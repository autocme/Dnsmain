#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import json
import logging

_logger = logging.getLogger(__name__)

class PortainerTemplateNew(models.Model):
    _name = 'j_portainer.template'
    _description = 'Portainer Template'
    _order = 'title'
    
    title = fields.Char('Title', required=True)
    description = fields.Text('Description')
    template_type = fields.Selection([
        ('1', 'Container'),
        ('2', 'Stack'),
        ('3', 'App Template')
    ], string='Type', default='1', required=True)
    platform = fields.Selection([
        ('linux', 'Linux'),
        ('windows', 'Windows')
    ], string='Platform', default='linux', required=True)
    template_id = fields.Integer('Template ID')
    logo = fields.Char('Logo URL')
    registry = fields.Char('Registry')
    image = fields.Char('Image')
    repository = fields.Text('Repository')
    categories = fields.Char('Categories')  # Store raw categories string
    category_ids = fields.Many2many('j_portainer.template.category', string='Categories Tags', compute='_compute_category_ids', store=True)
    environment_variables = fields.Text('Environment Variables')
    volumes = fields.Text('Volumes')
    ports = fields.Text('Ports')
    note = fields.Text('Note')
    details = fields.Text('Details', help="Additional details about the template")
    is_custom = fields.Boolean('Custom Template', default=False)
    
    # Custom template fields
    build_method = fields.Selection([
        ('editor', 'Web Editor'),
        ('repository', 'Git Repository')
    ], string='Build Method', default='editor')
    compose_file = fields.Text('Compose File', help="Docker Compose file content for the template")
    
    # Git repository fields
    git_authentication = fields.Boolean('Git Authentication', default=False)
    git_credentials_id = fields.Many2one('j_portainer.git.credentials', string='Git Credentials')
    git_username = fields.Char('Git Username')
    git_token = fields.Char('Git Token/Password')
    git_save_credential = fields.Boolean('Save Git Credentials', default=False)
    git_credential_name = fields.Char('Git Credential Name')
    git_repository_url = fields.Char('Git Repository URL')
    git_repository_reference = fields.Char('Git Repository Reference', help="Branch or tag name")
    git_compose_path = fields.Char('Git Compose Path', help="Path to the compose file in the repository")
    git_skip_tls = fields.Boolean('Skip TLS Verification', default=False)
    
    server_id = fields.Many2one('j_portainer.server', string='Server', required=True, ondelete='cascade')
    
    @api.depends('categories')
    def _compute_category_ids(self):
        """Compute category_ids from the categories string field.
        This handles the conversion from a comma-separated string to a Many2many field.
        """
        category_obj = self.env['j_portainer.template.category']
        
        for template in self:
            category_ids = []
            
            if template.categories:
                category_names = template.categories.split(',')
                for name in category_names:
                    name = name.strip()
                    if not name:
                        continue
                        
                    # Try to find existing category or create a new one
                    category = category_obj.search([('name', '=', name)], limit=1)
                    if not category:
                        category = category_obj.create({'name': name})
                    
                    category_ids.append(category.id)
                    
            template.category_ids = [(6, 0, category_ids)]  # Replace entire collection
    
    def _get_api(self):
        """Get API client"""
        return self.env['j_portainer.api']
    
    def get_formatted_env(self):
        """Get formatted environment variables"""
        self.ensure_one()
        if not self.environment_variables:
            return ''
            
        try:
            env_data = json.loads(self.environment_variables)
            result = []
            
            for var in env_data:
                name = var.get('name', '')
                label = var.get('label', '')
                default = var.get('default', '')
                description = var.get('description', '')
                
                if label:
                    result.append(f"{label} ({name}): {default}")
                    if description:
                        result.append(f"  {description}")
                else:
                    result.append(f"{name}: {default}")
                    if description:
                        result.append(f"  {description}")
                        
            return '\n'.join(result)
        except Exception as e:
            _logger.error(f"Error formatting environment variables: {str(e)}")
            return self.environment_variables
            
    def get_formatted_volumes(self):
        """Get formatted volumes"""
        self.ensure_one()
        if not self.volumes:
            return ''
            
        try:
            volumes_data = json.loads(self.volumes)
            result = []
            
            for volume in volumes_data:
                container = volume.get('container', '')
                bind = volume.get('bind', '')
                readonly = volume.get('readonly', False)
                
                if bind and container:
                    if readonly:
                        result.append(f"{bind} -> {container} (read-only)")
                    else:
                        result.append(f"{bind} -> {container}")
                        
            return '\n'.join(result)
        except Exception as e:
            _logger.error(f"Error formatting volumes: {str(e)}")
            return self.volumes
            
    def get_formatted_ports(self):
        """Get formatted ports"""
        self.ensure_one()
        if not self.ports:
            return ''
            
        try:
            ports_data = json.loads(self.ports)
            result = []
            
            for port in ports_data:
                container = port.get('container', '')
                host = port.get('host', '')
                protocol = port.get('protocol', 'tcp')
                
                if container:
                    if host:
                        result.append(f"{host}:{container}/{protocol}")
                    else:
                        result.append(f"{container}/{protocol}")
                        
            return '\n'.join(result)
        except Exception as e:
            _logger.error(f"Error formatting ports: {str(e)}")
            return self.ports
            
    def get_formatted_categories(self):
        """Get formatted categories"""
        self.ensure_one()
        if not self.categories:
            return ''
            
        return self.categories.replace(',', ', ')
        
    def get_formatted_details(self):
        """Get formatted details for the template"""
        self.ensure_one()
        if not self.details:
            return ''
            
        try:
            # If details is JSON, format it
            details_data = json.loads(self.details)
            if isinstance(details_data, dict):
                result = []
                for key, value in details_data.items():
                    if isinstance(value, (dict, list)):
                        result.append(f"{key}: {json.dumps(value, indent=2)}")
                    else:
                        result.append(f"{key}: {value}")
                return '\n'.join(result)
            return json.dumps(details_data, indent=2)
        except Exception as e:
            # If not JSON, return as is
            _logger.error(f"Error formatting details: {str(e)}")
            return self.details
    
    def get_type_name(self):
        """Get type name"""
        self.ensure_one()
        types = {
            '1': 'Container',
            '2': 'Stack',
            '3': 'App Template'
        }
        return types.get(self.template_type, 'Unknown')
        
    def action_deploy(self):
        """Action to deploy template"""
        self.ensure_one()
        
        return {
            'name': _('Deploy Template'),
            'type': 'ir.actions.act_window',
            'res_model': 'j_portainer.template.deploy.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_server_id': self.server_id.id,
                'default_template_id': self.id,
                'default_template_type': self.template_type,
                'default_template_title': self.title,
            }
        }
    
    def remove_custom_template(self):
        """Remove custom template
        Only works with custom templates
        """
        self.ensure_one()
        
        if not self.is_custom:
            raise UserError(_("Only custom templates can be removed"))
            
        try:
            api = self._get_api()
            result = api.template_action(
                self.server_id.id, self.template_id, 'delete')
                
            if result:
                # Delete the record
                self.unlink()
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Template Removed'),
                        'message': _('Template %s removed successfully') % self.title,
                        'sticky': False,
                        'type': 'success',
                    }
                }
            else:
                raise UserError(_("Failed to remove template"))
        except Exception as e:
            _logger.error(f"Error removing template {self.title}: {str(e)}")
            raise UserError(_("Error removing template: %s") % str(e))
    
    def action_refresh(self):
        """Refresh templates"""
        self.ensure_one()
        
        try:
            self.server_id.sync_templates()
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Templates Refreshed'),
                    'message': _('Templates refreshed successfully'),
                    'sticky': False,
                    'type': 'success',
                }
            }
        except Exception as e:
            _logger.error(f"Error refreshing templates: {str(e)}")
            raise UserError(_("Error refreshing templates: %s") % str(e))
            
    @api.model
    def create(self, vals):
        """Override create to handle custom templates creation in Portainer"""
        # Skip Portainer creation if skip_portainer_create flag is set (used during sync)
        if vals.get('is_custom') and not vals.get('skip_portainer_create'):
            # This is a custom template, create it in Portainer
            server_id = vals.get('server_id')
            if not server_id:
                raise UserError(_("Server is required for custom templates"))
                
            # Prepare template data for Portainer API
            template_data = self._prepare_template_data(vals)
            
            # Create template in Portainer
            try:
                api = self.env['j_portainer.api']
                server = self.env['j_portainer.server'].browse(server_id)
                
                response = api.create_template(server_id, template_data)
                
                if response and 'Id' in response:
                    # Template created successfully, set template_id
                    vals['template_id'] = response['Id']
                else:
                    raise UserError(_("Failed to create template in Portainer"))
                    
            except Exception as e:
                _logger.error(f"Error creating template in Portainer: {str(e)}")
                raise UserError(_("Error creating template in Portainer: %s") % str(e))
                
        # Create the record
        return super(PortainerTemplateNew, self).create(vals)
        
    def _prepare_template_data(self, vals):
        """Prepare template data for Portainer API"""
        # Set required fields with fallbacks if empty
        title = vals.get('title') or 'Custom Template'
        description = vals.get('description') or f'Template for {title}'
        
        template_data = {
            'type': int(vals.get('template_type', 1)),
            'title': title,
            'description': description,
            'note': vals.get('note', ''),
            'platform': vals.get('platform', 'linux'),
            'categories': vals.get('categories', '').split(',') if vals.get('categories') else []
        }
        
        # Clean up empty categories
        template_data['categories'] = [c.strip() for c in template_data['categories'] if c.strip()]
        
        # Ensure at least one category exists
        if not template_data['categories']:
            template_data['categories'] = ['Custom']
        
        # Handle build method for Stack templates (type 2)
        if template_data['type'] == 2:
            if vals.get('build_method') == 'editor':
                # Web editor method
                template_data['composeFileContent'] = vals.get('compose_file', '')
                
                # Ensure composeFileContent is not empty
                if not template_data['composeFileContent']:
                    template_data['composeFileContent'] = 'version: "3"\nservices:\n  app:\n    image: nginx:latest'
                    
            elif vals.get('build_method') == 'repository':
                # Git repository method
                git_data = {
                    'url': vals.get('git_repository_url', ''),
                    'referenceName': vals.get('git_repository_reference', 'master'),
                    'composeFilePath': vals.get('git_compose_path', 'docker-compose.yml'),
                }
                
                # Add TLS option if it exists
                if 'git_skip_tls' in vals:
                    git_data['skipTLSVerify'] = vals.get('git_skip_tls', False)
                
                # Handle authentication
                if vals.get('git_authentication'):
                    # Use credentials if provided
                    if vals.get('git_credentials_id'):
                        credentials = self.env['j_portainer.git.credentials'].browse(vals.get('git_credentials_id'))
                        git_data['authentication'] = {
                            'username': credentials.username,
                            'password': credentials.token
                        }
                    else:
                        # Use provided username/token
                        git_data['authentication'] = {
                            'username': vals.get('git_username', ''),
                            'password': vals.get('git_token', '')
                        }
                        
                        # Save credentials if requested
                        if vals.get('git_save_credential') and vals.get('git_credential_name'):
                            self._save_git_credentials(
                                vals.get('server_id'),
                                vals.get('git_credential_name'),
                                vals.get('git_username', ''),
                                vals.get('git_token', '')
                            )
                
                # Set repository fields
                template_data['repository'] = {
                    'url': git_data['url'],
                    'stackfile': git_data['composeFilePath']
                }
                
                if 'referenceName' in git_data:
                    template_data['repository']['reference'] = git_data['referenceName']
                    
                if 'skipTLSVerify' in git_data:
                    template_data['repository']['tlsSkipVerify'] = git_data['skipTLSVerify']
                    
                # Add authentication if present
                if 'authentication' in git_data:
                    template_data['repository']['authentication'] = {
                        'username': git_data['authentication']['username'],
                        'password': git_data['authentication']['password']
                    }
                
                # For compatibility with older Portainer versions
                template_data['repositoryURL'] = git_data['url']
                template_data['repositoryReferenceName'] = git_data['referenceName']
                template_data['composeFilePath'] = git_data['composeFilePath']
                template_data['repositoryAuthentication'] = bool(vals.get('git_authentication'))
                
                if template_data['repositoryAuthentication'] and 'authentication' in git_data:
                    template_data['repositoryUsername'] = git_data['authentication']['username']
                    template_data['repositoryPassword'] = git_data['authentication']['password']
                    
                if 'skipTLSVerify' in git_data:
                    template_data['skipTLSVerify'] = git_data['skipTLSVerify']
        
        # Add logging for debugging
        _logger.info(f"Prepared template data: {json.dumps(template_data, indent=2)}")
        
        return template_data
        
    def _save_git_credentials(self, server_id, name, username, token):
        """Save Git credentials for future use"""
        try:
            self.env['j_portainer.git.credentials'].create({
                'name': name,
                'username': username,
                'token': token,
                'server_id': server_id
            })
        except Exception as e:
            _logger.error(f"Error saving Git credentials: {str(e)}")
            # Don't raise exception, just log the error