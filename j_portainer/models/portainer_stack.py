#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import json
import logging

_logger = logging.getLogger(__name__)

class PortainerStack(models.Model):
    _name = 'j_portainer.stack'
    _description = 'Portainer Stack'
    _order = 'name'
    
    name = fields.Char('Name', required=True)
    stack_id = fields.Integer('Stack ID', required=True)
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
    content = fields.Text('Content', compute='_compute_content', store=True)
    creation_date = fields.Datetime('Created')
    update_date = fields.Datetime('Updated')
    details = fields.Text('Details')
    
    server_id = fields.Many2one('j_portainer.server', string='Server', required=True,
                                default=lambda self: self.env['j_portainer.server'].search([], limit=1))
    environment_id = fields.Many2one('j_portainer.environment', string='Environment', required=True,
                                    default=lambda self: self.env['j_portainer.environment'].search([], limit=1))
    last_sync = fields.Datetime('Last Synchronized', readonly=True)
    
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
                error_details = f"Server: {server.name}, Status: {server.status}"
                if server.error_message:
                    error_details += f", Last Error: {server.error_message}"
                
                raise UserError(f"Failed to create stack in Portainer. {error_details}")
            
            # If successful, the create_stack method triggers sync_stacks which creates the Odoo record
            # We need to find the newly created record and return it
            # Wait a moment for the sync to complete
            self.env.cr.commit()
            
            # Find the newly created stack
            new_stack = self.env['j_portainer.stack'].search([
                ('server_id', '=', server_id),
                ('environment_id', '=', environment_id),
                ('name', '=', name)
            ], limit=1, order='id desc')
            
            if new_stack:
                # Update any additional fields from vals that weren't set during sync
                update_vals = {}
                for field in ['build_method', 'git_repository_url', 'git_repository_reference', 
                              'git_compose_path', 'git_authentication', 'git_username', 'git_token']:
                    if field in vals:
                        update_vals[field] = vals[field]
                
                if update_vals:
                    new_stack.write(update_vals)
                
                return new_stack
            else:
                raise UserError("Stack was created in Portainer but sync failed. Please refresh the page.")
            
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

    @api.depends('content')
    def _compute_content(self):
        """Compute content field - now used directly for web editor"""
        # Content field is now used directly for both sync and manual editing
        pass
    
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
                self.server_id.id, self.stack_id, 'start', environment_id=self.environment_id)
            
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
                self.server_id.id, self.stack_id, 'stop', environment_id=self.environment_id)
            
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
                'default_environment_id': self.environment_id,
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
                self.server_id.id, self.stack_id, 'delete', environment_id=self.environment_id)
            
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
                
            # Make API request to create stack
            endpoint = '/api/stacks'
            _logger.info(f"Creating stack '{name}' on environment {environment_id} with data: {data}")
            
            response = server._make_api_request(endpoint, 'POST', data=data)
            
            _logger.info(f"Stack creation response: Status {response.status_code}, Content: {response.text}")
            
            if response.status_code in [200, 201, 204]:
                # Refresh stacks
                server.sync_stacks(environment_id)
                return True
            else:
                _logger.error(f"Failed to create stack '{name}': Status {response.status_code}, Response: {response.text}")
                return False
                
        except Exception as e:
            _logger.error(f"Error creating stack {name}: {str(e)}")
            return False