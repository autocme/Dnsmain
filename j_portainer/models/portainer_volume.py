#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import json
import logging

_logger = logging.getLogger(__name__)

class PortainerVolume(models.Model):
    _name = 'j_portainer.volume'
    _description = 'Portainer Volume'
    _order = 'name'
    
    name = fields.Char('Name', required=True, copy=False)
    volume_id = fields.Char('Volume ID', help="The unique identifier for this volume")
    driver = fields.Selection([
        ('local', 'Local'),
    ], string='Driver', required=True, default='local')
    driver_opts = fields.Text('Driver Options', help="Options passed to the volume driver")
    mountpoint = fields.Char('Mountpoint')
    created = fields.Datetime('Created')
    scope = fields.Char('Scope', default='local')
    labels = fields.Text('Labels')
    labels_html = fields.Html('Labels HTML', compute='_compute_labels_html')
    details = fields.Text('Details')
    in_use = fields.Boolean('In Use', default=False, help="Whether the volume is currently used by any containers")
    
    server_id = fields.Many2one('j_portainer.server', string='Server', required=True, default=lambda self: self._default_server_id())
    environment_id = fields.Many2one('j_portainer.environment', string='Environment', required=True, 
                                    domain="[('server_id', '=', server_id)]", default=lambda self: self._default_environment_id())
    last_sync = fields.Datetime('Last Synchronized', readonly=True)
    
    # Relation with containers using this volume
    container_volume_ids = fields.One2many('j_portainer.container.volume', 'volume_id', string='Container Mappings')
    container_count = fields.Integer('Container Count', compute='_compute_container_count', store=True)
    
    _sql_constraints = [
        ('unique_volume_per_environment', 'unique(server_id, environment_id, name)', 
         'Volume name must be unique per environment on each server'),
    ]
    
    def _default_server_id(self):
        """Default server selection"""
        return self.env['j_portainer.server'].search([('status', '=', 'connected')], limit=1)
    
    def _default_environment_id(self):
        """Default environment selection"""
        # Get the first server and then its first environment
        server = self._default_server_id()
        if server:
            return server.environment_ids[:1]
        return False
    
    @api.depends('container_volume_ids')
    def _compute_container_count(self):
        """Compute the number of containers using this volume"""
        for record in self:
            record.container_count = len(record.container_volume_ids)
    
    @api.model
    def create(self, vals):
        """Override create to automatically create volume in Portainer"""
        # If this is a sync operation from Portainer, save directly
        if self.env.context.get('sync_from_portainer'):
            return super().create(vals)
        
        # Create the Odoo record first to get the ID and validate fields
        volume = super().create(vals)
        
        try:
            # Create the volume in Portainer
            success = self._create_volume_in_portainer(volume)
            if not success:
                # If Portainer creation failed, delete the Odoo record and raise error
                volume.unlink()
                raise UserError(_("Failed to create volume in Portainer. Volume not created."))
                
        except Exception as e:
            # If any error occurs, clean up the Odoo record
            volume.unlink()
            error_msg = str(e)
            if "Failed to create volume in Portainer" in error_msg:
                raise  # Re-raise the UserError with the original message
            else:
                raise UserError(_("Error creating volume in Portainer: %s") % error_msg)
        
        return volume
    
    def _create_volume_in_portainer(self, volume):
        """Create volume in Portainer via API
        
        Args:
            volume: Volume record to create in Portainer
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Prepare data for volume creation
            data = {
                'Name': volume.name,
                'Driver': volume.driver
            }
            
            # Add driver options if provided
            if volume.driver_opts:
                try:
                    # Parse driver options as JSON if it's a string
                    import json
                    if isinstance(volume.driver_opts, str):
                        driver_opts = json.loads(volume.driver_opts)
                    else:
                        driver_opts = volume.driver_opts
                    data['DriverOpts'] = driver_opts
                except:
                    # If parsing fails, skip driver options
                    pass
            
            # Make API request to create volume
            endpoint = f'/api/endpoints/{volume.environment_id.environment_id}/docker/volumes/create'
            response = volume.server_id._make_api_request(endpoint, 'POST', data=data)
            
            if response.status_code in [200, 201, 204]:
                import json
                # Volume created successfully, get the volume details to update our record
                try:
                    volume_data = response.json()
                    # Update the volume record with data from Portainer
                    update_vals = {
                        'volume_id': volume_data.get('Name', volume.name),
                        'created': fields.Datetime.now(),
                        'mountpoint': volume_data.get('Mountpoint', ''),
                        'scope': volume_data.get('Scope', 'local'),
                        'details': json.dumps(volume_data, indent=2) if volume_data else '',
                    }

                    # Handle labels if present
                    if volume_data.get('Labels'):
                        import json
                        update_vals['labels'] = json.dumps(volume_data['Labels'])

                    # Write the updates without triggering create again
                    super(PortainerVolume, volume).write(update_vals)

                except Exception as e:
                    _logger.warning(f"Could not parse volume creation response: {e}")

                _logger.info(f"Volume '{volume.name}' created successfully in Portainer")
                return True
            else:
                # Extract detailed error message from Portainer response
                error_message = f"Status {response.status_code}"
                try:
                    if response.text:
                        error_data = response.json()
                        if 'message' in error_data:
                            error_message = error_data['message']
                        elif 'details' in error_data:
                            error_message = error_data['details']
                        else:
                            error_message = response.text
                    else:
                        error_message = f"HTTP {response.status_code} error with no response body"
                except:
                    # If JSON parsing fails, use raw response text
                    error_message = response.text if response.text else f"HTTP {response.status_code} error"
                
                _logger.error(f"Failed to create volume '{volume.name}': {error_message}")
                
                # Store the error for user display and raise UserError
                raise UserError(_("Failed to create volume in Portainer: %s") % error_message)
                
        except UserError:
            # Re-raise UserError without modification
            raise
        except Exception as e:
            _logger.error(f"Error creating volume '{volume.name}' in Portainer: {str(e)}")
            raise UserError(_("Error creating volume in Portainer: %s") % str(e))
            
    @api.depends('labels')
    def _compute_labels_html(self):
        """Format volume labels as HTML table"""
        for record in self:
            if not record.labels:
                record.labels_html = '<p>No labels found</p>'
                continue
                
            try:
                labels_data = json.loads(record.labels)
                if not labels_data:
                    record.labels_html = '<p>No labels found</p>'
                    continue
                    
                html = '<table class="table table-bordered table-sm">'
                html += '<thead><tr><th>Label Name</th><th>Value</th></tr></thead><tbody>'
                
                for key, value in labels_data.items():
                    html += f'<tr><td>{key}</td><td>{value}</td></tr>'
                    
                html += '</tbody></table>'
                record.labels_html = html
            except Exception as e:
                _logger.error(f"Error formatting labels HTML: {str(e)}")
                record.labels_html = f'<p>Error formatting labels: {str(e)}</p>'
    
    def _get_api(self):
        """Get API client"""
        return self.env['j_portainer.api']
    
    def get_formatted_labels(self):
        """Get formatted volume labels"""
        self.ensure_one()
        if not self.labels:
            return ''
            
        try:
            labels_data = json.loads(self.labels)
            formatted_labels = [f"{key}: {value}" for key, value in labels_data.items()]
            return '\n'.join(formatted_labels)
        except Exception as e:
            _logger.error(f"Error formatting labels: {str(e)}")
            return self.labels
    
    def get_formatted_details(self):
        """Get formatted volume details"""
        self.ensure_one()
        if not self.details:
            return ''
            
        try:
            details_data = json.loads(self.details)
            result = []
            
            # Extract some key information
            if 'Options' in details_data:
                options = details_data['Options']
                if options:
                    result.append("Options:")
                    for key, value in options.items():
                        result.append(f"  {key}: {value}")
                    
            # Format Usage if available
            if 'UsageData' in details_data:
                usage = details_data['UsageData']
                if usage and 'Size' in usage and 'RefCount' in usage:
                    result.append(f"Size: {self._format_size(usage['Size'])}")
                    result.append(f"Reference Count: {usage['RefCount']}")
                    
            return '\n'.join(result)
        except Exception as e:
            _logger.error(f"Error formatting details: {str(e)}")
            return self.details
    
    def _format_size(self, size_bytes):
        """Format size in bytes to human-readable format"""
        if not size_bytes or size_bytes == 0:
            return '0 B'
            
        size = float(size_bytes)
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
            
        return f"{size:.2f} PB"
    
    def remove(self):
        """Remove the volume"""
        self.ensure_one()
        
        # Store volume information before attempting to delete
        volume_name = self.name
        
        try:
            api = self._get_api()
            result = api.volume_action(
                self.server_id.id, self.environment_id.environment_id, self.name, 'delete')
            
            # Check for errors in the result - be very explicit about this check
            if isinstance(result, dict) and result.get('error'):
                error_message = result.get('error')
                _logger.error(f"Failed to remove volume {self.name} from Portainer: {error_message}")
                raise UserError(_(f"Failed to remove volume: {error_message}"))
                
            # Only consider it a success if result is a dict with success=True
            # or if result is True (for backward compatibility)
            if (isinstance(result, dict) and result.get('success')) or result is True:
                # Only delete the Odoo record if Portainer deletion was successful
                # Create success notification first, before deleting the record
                message = {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Volume Removed'),
                        'message': _('Volume %s removed successfully') % volume_name,
                        'sticky': False,
                        'type': 'success',
                    }
                }
                
                # Now delete the record
                self.unlink()
                self.env.cr.commit()
                
                return message
            else:
                # If Portainer deletion returned an unexpected result, don't delete from Odoo
                _logger.error(f"Unexpected result when removing volume {self.name} from Portainer: {result}")
                raise UserError(_("Failed to remove volume from Portainer - unexpected response"))
        except Exception as e:
            _logger.error(f"Error removing volume {self.name}: {str(e)}")
            raise UserError(_("Error removing volume: %s") % str(e))
    
    def action_remove(self):
        """Action to remove the volume from the UI"""
        return self.remove()
        
    def action_refresh(self):
        """Refresh volume information"""
        self.ensure_one()
        
        try:
            self.server_id.sync_volumes(self.environment_id.environment_id)
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Volume Refreshed'),
                    'message': _('Volume information refreshed successfully'),
                    'sticky': False,
                    'type': 'success',
                }
            }
        except Exception as e:
            _logger.error(f"Error refreshing volume {self.name}: {str(e)}")
            raise UserError(_("Error refreshing volume: %s") % str(e))
    
    @api.model
    def create_volume(self, server_id, environment_id, name, driver='local', labels=None):
        """Create a new volume
        
        Args:
            server_id: ID of the server to create the volume on
            environment_id: ID of the environment to create the volume on
            name: Name of the volume
            driver: Volume driver (default: 'local')
            labels: Dictionary of labels to apply to the volume
            
        Returns:
            bool: True if successful
        """
        try:
            server = self.env['j_portainer.server'].browse(server_id)
            if not server:
                return False
                
            # Prepare data for volume creation
            data = {
                'Name': name,
                'Driver': driver
            }
            
            if labels:
                data['Labels'] = labels
                
            # Make API request to create volume
            endpoint = f'/api/endpoints/{environment_id}/docker/volumes/create'
            response = server._make_api_request(endpoint, 'POST', data=data)
            
            if response.status_code in [200, 201, 204]:
                # Refresh volumes
                server.sync_volumes(environment_id)
                return True
            else:
                _logger.error(f"Failed to create volume: {response.text}")
                return False
                
        except Exception as e:
            _logger.error(f"Error creating volume {name}: {str(e)}")
            return False