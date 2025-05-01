#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class PortainerTemplateDeployWizard(models.TransientModel):
    _name = 'j_portainer.template.deploy.wizard'
    _description = 'Portainer Template Deployment Wizard'
    
    server_id = fields.Many2one('j_portainer.server', string='Server', required=True)
    template_id = fields.Many2one('j_portainer.template', string='Standard Template')
    custom_template_id = fields.Many2one('j_portainer.customtemplate', string='Custom Template')
    is_custom = fields.Boolean('Is Custom Template', default=False)
    
    # Template Info
    template_type = fields.Selection([
        ('1', 'Container'),
        ('2', 'Stack'),
        ('3', 'App Template')
    ], string='Type', default='1', required=True)
    template_title = fields.Char('Template Title', readonly=True)
    
    # Deployment options
    environment_id = fields.Many2one('j_portainer.environment', string='Environment', required=True, 
                                    domain="[('server_id', '=', server_id)]")
    name = fields.Char('Name', required=True, help="Name for the deployed container/stack")
    
    # Stack specific options
    stack_file_path = fields.Char('Stack File Path', help="Path to the compose file in the stack")
    env_vars = fields.Text('Environment Variables', help="Environment variables for the deployment")
    use_registry = fields.Boolean('Use Registry', help="Use a custom registry for the deployment")
    registry_url = fields.Char('Registry URL', help="Custom registry URL")
    enable_access_control = fields.Boolean('Enable Access Control', help="Enable access control for the stack")
    restart_policy = fields.Selection([
        ('no', 'No'),
        ('on-failure', 'On Failure'),
        ('always', 'Always'),
        ('unless-stopped', 'Unless Stopped')
    ], string='Restart Policy', default='always', help="Restart policy for the container")
    
    # Advanced options
    show_advanced = fields.Boolean('Show Advanced Options', default=False)
    enable_tls = fields.Boolean('Enable TLS', default=False)
    endpoint_id = fields.Char('Custom Endpoint ID')
    
    # Results
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Done'),
        ('error', 'Error')
    ], default='draft')
    result_message = fields.Text('Result', readonly=True)
    deployed_resource_id = fields.Char('Deployed Resource ID', readonly=True)
    compose_file_content = fields.Text('Compose File Content', readonly=True)
    
    @api.onchange('template_id', 'custom_template_id')
    def _onchange_template(self):
        """Handle template change"""
        if self.is_custom and self.custom_template_id:
            self.template_title = self.custom_template_id.title
            self.template_type = self.custom_template_id.template_type
            self.name = self.custom_template_id.title
        elif not self.is_custom and self.template_id:
            self.template_title = self.template_id.title
            self.template_type = self.template_id.template_type
            self.name = self.template_id.title
    
    def action_deploy(self):
        """Deploy the template"""
        self.ensure_one()
        
        if not self.environment_id:
            raise UserError(_("Environment is required"))
            
        if not self.name:
            raise UserError(_("Name is required"))
            
        # Prepare additional parameters
        params = {
            'name': self.name
        }
        
        # Add stack-specific options
        if self.template_type == '2':  # Stack
            params['stackfile'] = self.stack_file_path or ''
            
            # Add access control options
            if self.enable_access_control:
                params['enableAccessControl'] = True
                
            # Add custom endpoint ID if specified
            if self.endpoint_id:
                # Override the environment_id with the custom endpoint ID
                params['endpointId'] = self.endpoint_id
                
            # Add TLS options
            if self.enable_tls:
                params['tls'] = True
                
        # Add container-specific options
        if self.template_type == '1':  # Container
            # Add restart policy
            params['RestartPolicy'] = {'Name': self.restart_policy}
            
        # Parse environment variables
        if self.env_vars:
            env_dict = {}
            for line in self.env_vars.strip().split('\n'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    env_dict[key.strip()] = value.strip()
            
            if env_dict:
                params['env'] = env_dict
                
        # Add registry options
        if self.use_registry and self.registry_url:
            params['registry'] = self.registry_url
            
        # Get API client
        api = self.env['j_portainer.api']
        
        try:
            # Deploy through the API client
            result = None
            
            if self.is_custom:
                if not self.custom_template_id:
                    raise UserError(_("No custom template selected"))
                
                # Deploy custom template
                template_id = self.custom_template_id.template_id
                result = api.deploy_template(
                    self.server_id.id,
                    template_id,
                    self.environment_id.environment_id,
                    params,
                    is_custom=True
                )
            else:
                if not self.template_id:
                    raise UserError(_("No template selected"))
                
                # Deploy standard template
                template_id = self.template_id.template_id
                result = api.deploy_template(
                    self.server_id.id,
                    template_id,
                    self.environment_id.environment_id,
                    params,
                    is_custom=False
                )
                
            # Handle result
            if result:
                # Store deployment information
                result_data = {
                    'state': 'done',
                    'result_message': _("Template '%s' deployed successfully!") % self.template_title
                }
                
                # Extract additional information from result
                if isinstance(result, dict):
                    if 'Id' in result:
                        result_data['deployed_resource_id'] = result['Id']
                    elif 'id' in result:
                        result_data['deployed_resource_id'] = result['id']
                    elif 'container_id' in result:
                        result_data['deployed_resource_id'] = result['container_id']
                        
                    # For stack deployments, store compose file content if available
                    if self.template_type == '2' and self.is_custom and self.custom_template_id.compose_file:
                        result_data['compose_file_content'] = self.custom_template_id.compose_file
                        
                # Update wizard record
                self.write(result_data)
                
                # Refresh resources after deployment
                self.server_id.sync_containers(self.environment_id.environment_id)
                if self.template_type == '2':  # Stack
                    self.server_id.sync_stacks(self.environment_id.environment_id)
                
                # Determine the appropriate resource type name for the message
                resource_type = 'container'
                if self.template_type == '2':
                    resource_type = 'stack'
                elif self.template_type == '3':
                    resource_type = 'application'
                
                # Return success message
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Deployment Successful'),
                        'message': _("Template '%s' deployed successfully as %s! Resources have been refreshed.") % (self.template_title, resource_type),
                        'sticky': False,
                        'type': 'success',
                    }
                }
            else:
                self.write({
                    'state': 'error',
                    'result_message': _("Failed to deploy template")
                })
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Deployment Failed'),
                        'message': _("Failed to deploy template"),
                        'sticky': True,
                        'type': 'danger',
                    }
                }
                
        except Exception as e:
            _logger.error(f"Error deploying template: {str(e)}")
            self.write({
                'state': 'error',
                'result_message': _("Error: %s") % str(e)
            })
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Deployment Error'),
                    'message': _("Error: %s") % str(e),
                    'sticky': True,
                    'type': 'danger',
                }
            }