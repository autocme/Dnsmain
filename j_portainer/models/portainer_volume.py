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
    
    name = fields.Char('Name', required=True)
    volume_id = fields.Char('Volume ID', help="The unique identifier for this volume")
    driver = fields.Char('Driver', required=True)
    driver_opts = fields.Text('Driver Options', help="Options passed to the volume driver")
    mountpoint = fields.Char('Mountpoint')
    created = fields.Datetime('Created')
    scope = fields.Char('Scope', default='local')
    labels = fields.Text('Labels')
    details = fields.Text('Details')
    in_use = fields.Boolean('In Use', default=False, help="Whether the volume is currently used by any containers")
    
    server_id = fields.Many2one('j_portainer.server', string='Server', required=True, ondelete='cascade')
    environment_id = fields.Integer('Environment ID', required=True)
    environment_name = fields.Char('Environment', required=True)
    
    # Relation with containers using this volume
    container_volume_ids = fields.One2many('j_portainer.container.volume', 'volume_id', string='Container Mappings')
    container_count = fields.Integer('Container Count', compute='_compute_container_count', store=True)
    
    @api.depends('container_volume_ids')
    def _compute_container_count(self):
        """Compute the number of containers using this volume"""
        for record in self:
            record.container_count = len(record.container_volume_ids)
    
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
                self.server_id.id, self.environment_id, self.name, 'delete')
                
            if result:
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
                # If Portainer deletion failed, don't delete from Odoo
                _logger.error(f"Failed to remove volume {self.name} from Portainer")
                raise UserError(_("Failed to remove volume from Portainer"))
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
            self.server_id.sync_volumes(self.environment_id)
            
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