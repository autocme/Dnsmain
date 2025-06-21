#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import json
import logging
import re

_logger = logging.getLogger(__name__)

class PortainerStack(models.Model):
    _name = 'j_portainer.stack'
    _description = 'Portainer Stack'
    _order = 'name'
    
    name = fields.Char('Name', required=True)
    stack_id = fields.Integer('Stack ID', required=False, copy=False)
    type = fields.Selection([
        ('1', 'Swarm'),
        ('2', 'Compose')
    ], string='Type', default='2', required=True)
    status = fields.Selection([
        ('0', 'Unknown'),
        ('1', 'Active'),
        ('2', 'Inactive')
    ], string='Status', default='0')
    file_content = fields.Text('Stack File')
    content = fields.Text('Content')
    creation_date = fields.Datetime('Created')
    update_date = fields.Datetime('Updated')
    details = fields.Text('Details')
    
    server_id = fields.Many2one('j_portainer.server', string='Server', required=True,
                                default=lambda self: self.env['j_portainer.server'].search([], limit=1))
    environment_id = fields.Many2one('j_portainer.environment', string='Environment', required=True,
                                    default=lambda self: self.env['j_portainer.environment'].search([], limit=1))
    environment_name = fields.Char('Environment Name', related='environment_id.name', readonly=True, store=True)
    last_sync = fields.Datetime('Last Synchronized', readonly=True)
    
    # Custom template relationship
    custom_template_id = fields.Many2one('j_portainer.customtemplate', string='Custom Template',
                                        help='The custom template this stack was created from')
    
    # Build functionality fields
    build_method = fields.Selection([
        ('web_editor', 'Web Editor'),
        ('upload', 'Upload'),
        ('repository', 'Repository')
    ], string='Build Method', required=True, default='web_editor')
    
    # Repository details
    git_repository_url = fields.Char('Repository URL')
    git_repository_reference = fields.Char('Reference', help="Branch, tag, or commit hash")
    git_compose_path = fields.Char('Compose File Path', default='docker-compose.yml')
    git_skip_tls = fields.Boolean('Skip TLS Verification', default=False)
    git_authentication = fields.Boolean('Use Authentication', default=False)
    git_credentials_id = fields.Many2one('j_portainer.git.credentials', string='Git Credentials')
    git_username = fields.Char('Username')
    git_token = fields.Char('Token/Password')
    git_save_credential = fields.Boolean('Save Credentials', default=False)
    git_credential_name = fields.Char('Credential Name')
    
    # Upload field
    compose_file_upload = fields.Binary('Compose File Upload',
                                      help='You can upload a compose file from your computer.')
    
    # Related containers in this stack
    container_ids = fields.One2many('j_portainer.container', 'stack_id', string='Containers')
    
    # Volume-related fields
    volume_count = fields.Integer('Volume Count', compute='_compute_volume_stats', )
    total_volume_size = fields.Char('Total Volume Size', compute='_compute_volume_stats', )
    
    _sql_constraints = [
        ('unique_stack_per_environment', 'unique(server_id, environment_id, stack_id)', 
         'Stack ID must be unique per environment on each server'),
    ]
    
    @api.onchange('build_method')
    def _onchange_build_method(self):
        """Clear fields when build method changes"""
        if self.build_method == 'web_editor':
            # Clear repository and upload fields
            self.git_repository_url = False
            self.git_repository_reference = False
            self.git_compose_path = False
            self.git_skip_tls = False
            self.git_authentication = False
            self.git_credentials_id = False
            self.git_username = False
            self.git_token = False
            self.git_save_credential = False
            self.git_credential_name = False
            self.compose_file_upload = False
        elif self.build_method == 'repository':
            # Clear content and upload fields
            self.content = False
            self.compose_file_upload = False
        elif self.build_method == 'upload':
            # Clear content and repository fields
            self.content = False
            self.git_repository_url = False
            self.git_repository_reference = False
            self.git_compose_path = False
            self.git_skip_tls = False
            self.git_authentication = False
            self.git_credentials_id = False
            self.git_username = False
            self.git_token = False
            self.git_save_credential = False
            self.git_credential_name = False

    @api.depends('container_ids', 'container_ids.volume_ids', 'container_ids.volume_ids.usage_size')
    def _compute_volume_stats(self):
        """Compute volume count and total size for this stack"""
        for record in self:
            # Get volume mappings from all containers in this stack
            volume_mappings = record.container_ids.mapped('volume_ids').filtered(lambda v: v.type == 'volume' and v.volume_id)
            
            # Count unique volumes (not mappings) to avoid duplicates
            unique_volume_ids = set(volume_mappings.mapped('volume_id.id'))
            record.volume_count = len(unique_volume_ids)
            
            # Sum usage_size values with proper unit conversion
            # Group by volume_id to avoid counting the same volume multiple times
            volume_sizes_bytes = {}
            for mapping in volume_mappings:
                if mapping.volume_id and mapping.usage_size and mapping.usage_size not in ['Error', 'N/A', '']:
                    volume_id = mapping.volume_id.id
                    if volume_id not in volume_sizes_bytes:
                        try:
                            # Extract numeric value and unit from usage_size (e.g., "4.0K" -> 4.0 and "K")
                            size_match = re.match(r'^(\d+\.?\d*)\s*([KMGT]?)B?$', mapping.usage_size.upper().strip())
                            if size_match:
                                size_value = float(size_match.group(1))
                                unit = size_match.group(2)
                                
                                # Convert to bytes based on unit
                                multipliers = {
                                    '': 1,          # bytes
                                    'K': 1024,      # kilobytes
                                    'M': 1024**2,   # megabytes
                                    'G': 1024**3,   # gigabytes
                                    'T': 1024**4,   # terabytes
                                }
                                
                                size_bytes = size_value * multipliers.get(unit, 1)
                                volume_sizes_bytes[volume_id] = size_bytes
                        except (ValueError, AttributeError):
                            continue
            
            # Sum all unique volume sizes in bytes
            total_bytes = sum(volume_sizes_bytes.values())
            
            # Convert back to human readable format with 2 decimal precision
            if total_bytes == 0:
                record.total_volume_size = "0B"
            elif total_bytes < 1024:
                record.total_volume_size = f"{total_bytes:.0f}B"
            elif total_bytes < 1024**2:
                record.total_volume_size = f"{total_bytes/1024:.2f}K"
            elif total_bytes < 1024**3:
                record.total_volume_size = f"{total_bytes/(1024**2):.2f}M"
            elif total_bytes < 1024**4:
                record.total_volume_size = f"{total_bytes/(1024**3):.2f}G"
            else:
                record.total_volume_size = f"{total_bytes/(1024**4):.2f}T"

    def write(self, vals):
        """Override write to handle content updates"""
        return super(PortainerStack, self).write(vals)

    @api.model
    def create(self, vals):
        """Override create to create stack in Portainer first"""
        # If stack_id is provided, this is a sync operation - save directly
        record = super(PortainerStack, self).create(vals)

        if vals.get('stack_id'):
            return record

        # Auto-create in Portainer using the separated method
        # If this fails, it will raise UserError and prevent record creation
        record.create_stack_in_portainer()

        # If create_stack_in_portainer returns a notification action, we still return the record
        # The notification will be handled by the calling method
        return record
    
    def _parse_portainer_date(self, date_value):
        """Parse Portainer date format to Odoo datetime"""
        if not date_value:
            return False
        try:
            # Handle Unix timestamp
            if isinstance(date_value, (int, float)):
                return fields.Datetime.from_timestamp(date_value)
            # Handle ISO string
            elif isinstance(date_value, str):
                return fields.Datetime.from_string(date_value)
        except:
            return False
        return False


    
    def _get_api(self):
        """Get API client"""
        return self.env['j_portainer.api']
    
    def get_type_name(self):
        """Get type name"""
        self.ensure_one()
        types = {
            1: 'Swarm',
            2: 'Compose'
        }
        return types.get(self.type, 'Unknown')
        
    def get_status_name(self):
        """Get status name"""
        self.ensure_one()
        statuses = {
            1: 'Active',
            2: 'Inactive'
        }
        return statuses.get(self.status, 'Unknown')
        
    def get_status_color(self):
        """Get status color"""
        self.ensure_one()
        colors = {
            1: 'success',
            2: 'danger'
        }
        return colors.get(self.status, 'secondary')
    
    def start(self):
        """Start the stack"""
        self.ensure_one()
        
        try:
            api = self._get_api()
            result = api.stack_action(
                self.server_id.id, self.stack_id, 'start', environment_id=self.environment_id.environment_id)
            
            # Check if the result is True (success) or a dict with error info
            if result is True:
                # Only update status if the operation was successful
                self.write({'status': '1'})
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Stack Started'),
                        'message': _('Stack %s started successfully') % self.name,
                        'sticky': False,
                        'type': 'success',
                    }
                }
            else:
                # If result is a dict, it contains error information
                error_msg = result.get('error', 'Unknown error') if isinstance(result, dict) else str(result)
                _logger.error(f"Failed to start stack {self.name}: {error_msg}")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Start Failed'),
                        'message': _('Failed to start stack %s: %s') % (self.name, error_msg),
                        'sticky': True,
                        'type': 'danger',
                    }
                }
        except Exception as e:
            _logger.error(f"Error starting stack {self.name}: {str(e)}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('Error starting stack %s: %s') % (self.name, str(e)),
                    'sticky': True,
                    'type': 'danger',
                }
            }
    
    def stop(self):
        """Stop the stack"""
        self.ensure_one()
        
        try:
            api = self._get_api()
            result = api.stack_action(
                self.server_id.id, self.stack_id, 'stop', environment_id=self.environment_id.environment_id)
            
            # Check if the result is True (success) or a dict with error info
            if result is True:
                # Only update status if the operation was successful
                self.write({'status': '2'})
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Stack Stopped'),
                        'message': _('Stack %s stopped successfully') % self.name,
                        'sticky': False,
                        'type': 'success',
                    }
                }
            else:
                # If result is a dict, it contains error information
                error_msg = result.get('error', 'Unknown error') if isinstance(result, dict) else str(result)
                _logger.error(f"Failed to stop stack {self.name}: {error_msg}")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Stop Failed'),
                        'message': _('Failed to stop stack %s: %s') % (self.name, error_msg),
                        'sticky': True,
                        'type': 'danger',
                    }
                }
        except Exception as e:
            _logger.error(f"Error stopping stack {self.name}: {str(e)}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('Error stopping stack %s: %s') % (self.name, str(e)),
                    'sticky': True,
                    'type': 'danger',
                }
            }
    
    def update(self):
        """Update the stack"""
        self.ensure_one()
        
        return {
            'name': _('Update Stack'),
            'type': 'ir.actions.act_window',
            'res_model': 'j_portainer.stack.update.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_server_id': self.server_id.id,
                'default_stack_id': self.id,
                'default_stack_name': self.name,
                'default_environment_id': self.environment_id.id,
                'default_current_file': self.file_content,
            }
        }
    
    def remove(self):
        """Remove the stack"""
        self.ensure_one()
        
        # Store stack information before attempting to delete
        stack_name = self.name
        
        try:
            api = self._get_api()
            result = api.stack_action(
                self.server_id.id, self.stack_id, 'delete', environment_id=self.environment_id.environment_id)
            
            # Check for errors in the result - be very explicit about this check
            if isinstance(result, dict) and result.get('error'):
                error_message = result.get('error')
                _logger.error(f"Failed to remove stack {self.name} from Portainer: {error_message}")
                raise UserError(_(f"Failed to remove stack: {error_message}"))
                
            # Only consider it a success if result is a dict with success=True
            # or if result is True (for backward compatibility)
            if (isinstance(result, dict) and result.get('success')) or result is True:
                # Only delete the Odoo record if Portainer deletion was successful
                # Create success notification first, before deleting the record
                message = {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Stack Removed'),
                        'message': _('Stack %s removed successfully') % stack_name,
                        'sticky': False,
                        'type': 'success',
                    }
                }
                
                # Before deleting the record, clear the stack_id reference on any containers
                # This ensures we don't have orphaned references
                if self.container_ids:
                    self.container_ids.write({'stack_id': False})
                
                # Now delete the record
                self.unlink()
                self.env.cr.commit()
                
                return message
            else:
                # If Portainer deletion returned an unexpected result, don't delete from Odoo
                _logger.error(f"Unexpected result when removing stack {self.name} from Portainer: {result}")
                raise UserError(_("Failed to remove stack from Portainer - unexpected response"))
        except Exception as e:
            _logger.error(f"Error removing stack {self.name}: {str(e)}")
            raise UserError(_("Error removing stack: %s") % str(e))
    
    def action_start(self):
        """Action to start the stack (wrapper for start method)"""
        return self.start()
        
    def action_stop(self):
        """Action to stop the stack (wrapper for stop method)"""
        return self.stop()
        
    def action_remove(self):
        """Action to remove the stack (wrapper for remove method)"""
        return self.remove()
    
    def action_open_migration_wizard(self):
        """Open stack migration/duplication wizard"""
        self.ensure_one()
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Stack Migration/Duplication'),
            'res_model': 'j_portainer.stack_migration_wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_source_stack_id': self.id,
                'active_id': self.id,
                'active_model': 'j_portainer.stack'
            }
        }
    
    def action_view_volumes(self):
        """Smart button action to view volumes used by this stack"""
        self.ensure_one()
        
        # Get all volumes from containers in this stack
        volumes = self.container_ids.mapped('volume_ids.volume_id')
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Stack Volumes'),
            'res_model': 'j_portainer.volume',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', volumes.ids)],
            'context': {
                'default_server_id': self.server_id.id,
                'default_environment_id': self.environment_id.id,
            }
        }


    def action_sync_stack_resources(self):
        try:
            self.server_id.sync_volumes(self.environment_id.environment_id)
            self.server_id.sync_networks(self.environment_id.environment_id)
            self.server_id.sync_containers(self.environment_id.environment_id)

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Stack Resources Synchronized'),
                    'message': _('All resources for stack %s have been synchronized') % self.name,
                    'sticky': False,
                    'type': 'success',
                }
            }
        except Exception as e:
            _logger.error(f"Error syncing environment {self.name}: {str(e)}")
            raise UserError(_("Error syncing environment: %s") % str(e))
    # @api.model
    def create_stack_in_portainer(self):
        """Create this stack in Portainer
        
        Raises:
            UserError: If stack creation fails in Portainer
        """
        self.ensure_one()
        
        # Validate required fields
        if not self.content:
            raise UserError(_("Stack content is required to create stack in Portainer"))
        
        try:
            server = self.server_id
            if not server:
                raise UserError(_("Server is required to create stack in Portainer"))
                
            environment = self.environment_id
            if not environment:
                raise UserError(_("Environment is required to create stack in Portainer"))
            
            # Validate stack creation is allowed in this environment
            environment.validate_stack_creation()
                
            # Use the correct Portainer API endpoint for stack creation
            endpoint = f'/api/stacks/create/standalone/string?endpointId={environment.environment_id}'
            
            # Prepare the payload according to the API specification
            stack_payload = {
                'Name': self.name,
                'StackFileContent': self.content
            }
            
            _logger.info(f"Creating stack '{self.name}' using endpoint: {endpoint}")
            _logger.info(f"Stack payload: {stack_payload}")
            
            # Use longer timeout for stack creation as it can take time
            response = server._make_api_request(endpoint, 'POST', data=stack_payload)
            
            _logger.info(f"Stack creation response: Status {response.status_code}, Content: {response.text}")
            
            if response.status_code in [200, 201, 204]:
                # Update stack with actual values from Portainer response
                update_vals = {'status': '1'}  # Active
                
                try:
                    if response.text:
                        response_data = response.json()
                        _logger.info(f"Portainer response data: {response_data}")
                        
                        # Extract stack ID
                        if 'Id' in response_data:
                            update_vals['stack_id'] = response_data['Id']
                        
                        # Extract other relevant fields from response
                        if 'Name' in response_data:
                            update_vals['name'] = response_data['Name']
                        
                        if 'Type' in response_data:
                            update_vals['type'] = str(response_data['Type'])
                        
                        if 'CreationDate' in response_data:
                            update_vals['creation_date'] = self._parse_portainer_date(response_data['CreationDate'])
                        
                        if 'UpdatedDate' in response_data:
                            update_vals['update_date'] = self._parse_portainer_date(response_data['UpdatedDate'])
                        
                        # Store the original file content
                        if 'StackFileContent' in response_data:
                            update_vals['file_content'] = response_data['StackFileContent']
                        
                        # Store any additional details
                        if 'Status' in response_data:
                            # Map Portainer status to our status
                            portainer_status = response_data['Status']
                            if portainer_status == 1:
                                update_vals['status'] = '1'  # Active
                            elif portainer_status == 2:
                                update_vals['status'] = '2'  # Inactive
                            else:
                                update_vals['status'] = '0'  # Unknown
                        
                        # Store full response as details for debugging
                        update_vals['details'] = str(response_data)
                        
                except Exception as parse_error:
                    _logger.warning(f"Could not parse Portainer response: {str(parse_error)}")
                    # Still proceed with basic status update
                
                # Update the stack record with response data
                self.write(update_vals)
                
                # Refresh stacks and containers to ensure everything is in sync
                # server.sync_stacks(environment.environment_id)
                # server.sync_volumes(environment.environment_id)
                # server.sync_networks(environment.environment_id)
                # server.sync_containers(environment.environment_id)
                
                _logger.info(f"Stack '{self.name}' created successfully in Portainer with ID {self.stack_id}")
                
                # Return success action for UI feedback
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Stack Created Successfully'),
                        'message': _('Stack "%s" has been created in Portainer successfully with ID %s.') % (self.name, self.stack_id),
                        'type': 'success',
                        'sticky': False,
                    }
                }
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
                
                _logger.error(f"Failed to create stack '{self.name}': Status {response.status_code}, Response: {response.text}")
                raise UserError(_("Failed to create stack in Portainer: %s") % error_message)
                
        except UserError:
            raise
        except Exception as e:
            _logger.error(f"Error creating stack {self.name}: {str(e)}")
            raise UserError(_("Error creating stack in Portainer: %s") % str(e))

    def action_redeploy_stack(self):
        """Re-deploy (update) stack in Portainer with current content"""
        self.ensure_one()
        
        # Validate required fields
        if not self.stack_id or self.stack_id == 0:
            raise UserError(_("Cannot re-deploy: Stack does not exist in Portainer"))
        
        if not self.content:
            raise UserError(_("Cannot re-deploy: Stack content is required"))
        
        try:
            server = self.server_id
            if not server:
                raise UserError(_("Server is required to re-deploy stack"))
                
            environment = self.environment_id
            if not environment:
                raise UserError(_("Environment is required to re-deploy stack"))
            
            # Use Portainer API endpoint for stack updates
            endpoint = f'/api/stacks/{self.stack_id}?endpointId={environment.environment_id}'
            
            # Prepare the payload for stack update according to API specification
            update_payload = {
                'StackFileContent': self.content,
                'Env': []  # Environment variables (empty for now)
            }
            
            _logger.info(f"Re-deploying stack '{self.name}' (ID: {self.stack_id}) using endpoint: {endpoint}")
            _logger.info(f"Update payload: {update_payload}")
            
            # Make PUT request to update the stack
            response = server._make_api_request(endpoint, 'PUT', data=update_payload)
            
            _logger.info(f"Stack update response: Status {response.status_code}, Content: {response.text}")
            
            if response.status_code in [200, 201, 204]:
                # Update stack fields with response data if available
                update_vals = {}
                
                try:
                    if response.text:
                        response_data = response.json()
                        _logger.info(f"Portainer update response data: {response_data}")
                        
                        # Update timestamp fields
                        if 'UpdatedDate' in response_data:
                            update_vals['update_date'] = self._parse_portainer_date(response_data['UpdatedDate'])
                        else:
                            # Set current timestamp if not provided
                            update_vals['update_date'] = fields.Datetime.now()
                        
                        # Update file content if returned
                        if 'StackFileContent' in response_data:
                            update_vals['file_content'] = response_data['StackFileContent']
                        
                        # Update status if provided
                        if 'Status' in response_data:
                            portainer_status = response_data['Status']
                            if portainer_status == 1:
                                update_vals['status'] = '1'  # Active
                            elif portainer_status == 2:
                                update_vals['status'] = '2'  # Inactive
                            else:
                                update_vals['status'] = '0'  # Unknown
                        
                        # Store updated response details
                        update_vals['details'] = str(response_data)
                        
                except Exception as parse_error:
                    _logger.warning(f"Could not parse update response: {str(parse_error)}")
                    # Still set update timestamp
                    update_vals['update_date'] = fields.Datetime.now()
                
                # Update the stack record
                if update_vals:
                    self.write(update_vals)
                
                # Sync resources after successful update
                server.sync_stacks(environment.environment_id)
                server.sync_volumes(environment.environment_id)
                server.sync_networks(environment.environment_id)
                server.sync_containers(environment.environment_id)
                
                _logger.info(f"Stack '{self.name}' re-deployed successfully in Portainer")
                
                # Return success notification
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Stack Re-deployed Successfully'),
                        'message': _('Stack "%s" has been re-deployed in Portainer successfully.') % self.name,
                        'type': 'success',
                        'sticky': False,
                    }
                }
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
                
                _logger.error(f"Failed to re-deploy stack '{self.name}': Status {response.status_code}, Response: {response.text}")
                raise UserError(_("Failed to re-deploy stack in Portainer: %s") % error_message)
                
        except UserError:
            raise
        except Exception as e:
            _logger.error(f"Error re-deploying stack {self.name}: {str(e)}")
            raise UserError(_("Error re-deploying stack in Portainer: %s") % str(e))