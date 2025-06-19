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
    stack_id = fields.Integer('Stack ID', required=True, copy=False)
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
        if vals.get('stack_id'):
            return super().create(vals)
        
        # New stack creation - create in Portainer first using existing method
        try:
            # Get required data
            server_id = vals.get('server_id')
            environment_id = vals.get('environment_id')
            name = vals.get('name')
            build_method = vals.get('build_method', 'web_editor')
            
            if not all([server_id, environment_id, name]):
                raise UserError("Server, Environment, and Name are required to create a stack.")
            
            # Get environment record to get the environment_id for Portainer API
            environment = self.env['j_portainer.environment'].browse(environment_id)
            if not environment.exists():
                raise UserError("Invalid environment specified.")
            
            # Validate stack creation is allowed in this environment
            environment.validate_stack_creation()
            
            # Prepare stack content based on build method
            stack_file_content = ''
            
            if build_method == 'web_editor':
                content = vals.get('content')
                if not content:
                    raise UserError("Stack content is required for Web Editor method.")
                stack_file_content = content
                
            elif build_method == 'upload':
                # Handle file upload - would need to process the binary file
                if not vals.get('compose_file_upload'):
                    raise UserError("Compose file upload is required for Upload method.")
                # TODO: Process uploaded file content
                raise UserError("File upload method is not yet implemented.")
                
            elif build_method == 'repository':
                # For repository method, we'll need to enhance the create_stack method
                # For now, raise an error as repository method needs different handling
                raise UserError("Repository method is not yet supported for direct creation. Use Web Editor method.")
            
            # Use the existing create_stack method
            _logger.info(f"Creating stack {name} in Portainer using environment ID {environment.environment_id}")
            
            success = self.create_stack(
                server_id=server_id,
                environment_id=environment.environment_id,  # Use the Portainer environment ID
                name=name,
                stack_file_content=stack_file_content,
                deployment_method=1  # File method
            )
            
            if not success:
                # Get the server to check its status and last error
                server = self.env['j_portainer.server'].browse(server_id)
                
                # Show the actual error message if available
                if server.error_message:
                    raise UserError(f"Failed to create stack in Portainer: {server.error_message}")
                else:
                    error_details = f"Server: {server.name}, Status: {server.status}"
                    raise UserError(f"Failed to create stack in Portainer. {error_details}")
            
            # Stack creation successful in Portainer
            _logger.info(f"Stack {name} successfully created in Portainer")
            return True
            
        except UserError:
            raise
        except Exception as e:
            _logger.error(f"Error creating stack: {str(e)}")
            raise UserError(f"Failed to create stack: {str(e)}")
    
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

    
    @api.model
    def create_stack(self, server_id, environment_id, name, stack_file_content, deployment_method=1):
        """Create a new stack
        
        Args:
            server_id: ID of the server to create the stack on
            environment_id: ID of the environment to create the stack on
            name: Name of the stack
            stack_file_content: Content of the stack file (docker-compose.yml)
            deployment_method: Deployment method (1 = File, 2 = String)
            
        Returns:
            bool: True if successful
        """
        try:
            server = self.env['j_portainer.server'].browse(server_id)
            if not server:
                return False
                
            # Prepare data for stack creation
            data = {
                'Name': name,
                'StackFileContent': stack_file_content,
                'Environment': [],
                'EndpointId': environment_id,
                'SwarmID': '',
                'Type': 2  # Compose (API expects integer here)
            }
                
            # Use the correct Portainer API endpoint for stack creation
            endpoint = f'/api/stacks/create/standalone/string?endpointId={environment_id}'
            
            # Prepare the payload according to the API specification
            stack_payload = {
                'Name': name,
                'StackFileContent': stack_file_content
            }
            
            _logger.info(f"Creating stack '{name}' using endpoint: {endpoint}")
            _logger.info(f"Stack payload: {stack_payload}")
            
            # Use longer timeout for stack creation as it can take time
            response = server._make_api_request(endpoint, 'POST', data=stack_payload)
            
            _logger.info(f"Stack creation response: Status {response.status_code}, Content: {response.text}")
            
            if response.status_code in [200, 201, 204]:
                # Refresh stacks and containers
                server.sync_stacks(environment_id)
                server.sync_volumes(environment_id)
                server.sync_containers(environment_id)
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
                
                # Store the detailed error message in server for user display
                server.error_message = f"Failed to create stack '{name}': {error_message}"
                
                _logger.error(f"Failed to create stack '{name}': Status {response.status_code}, Response: {response.text}")
                return False
                
        except Exception as e:
            _logger.error(f"Error creating stack {name}: {str(e)}")
            return False