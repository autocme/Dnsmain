#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import json
import logging

_logger = logging.getLogger(__name__)

class PortainerCustomTemplate(models.Model):
    _name = 'j_portainer.customtemplate'
    _description = 'Portainer Custom Template'
    _order = 'title'
    _inherit = ['j_portainer.template.mixin']
    _copy_default_excluded_fields = [
        'template_id', 
        'fileContent',
        'compose_file',
        'repository',
        'volumes',
        'ports',
        'environment_variables'
    ]
    _rec_name='title'
    
    is_custom = fields.Boolean('Custom Template', default=True, help="Used to identify custom templates")
    
    title = fields.Char('Title', required=True)
    description = fields.Text('Description')
    template_type = fields.Selection([
        ('1', 'Swarm'),
        ('2', 'Standalone / Podman')
    ], string='Type', default='2', required=True)
    platform = fields.Selection([
        ('linux', 'Linux'),
        ('windows', 'Windows')
    ], string='Platform', default='linux', required=True)
    template_id = fields.Char('Template ID', copy=False)
    server_id = fields.Many2one('j_portainer.server', string='Server', required=True, default=lambda self: self._default_server_id())
    last_sync = fields.Datetime('Last Synchronized', readonly=True)
    environment_id = fields.Many2one('j_portainer.environment', string='Environment', required=True,
                                domain="[('server_id', '=', server_id)]", default=lambda self: self._default_environment_id())
    stack_id = fields.Many2one('j_portainer.stack', string='Stack', required=False)
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
    skip_portainer_create = fields.Boolean('Skip Portainer Creation', default=False, 
                                          help='Used during sync to skip creating the template in Portainer')
    manual_template_id = fields.Char('Manual Template ID', copy=False,
                                      help='Template ID for manually created templates in Portainer - use this if automatic creation fails')
    
    # Custom Template specific fields
    build_method = fields.Selection([
        ('editor', 'Web Editor'),
        ('file', 'File Upload'),
        ('repository', 'Git Repository')
    ], string='Build Method', default='editor', required=True)
    
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
    
    # Editor method fields
    fileContent = fields.Text('File Content', help="Content of the template file (Docker Compose or Stack file)")
    
    # File upload method fields
    upload_file = fields.Binary('Upload File', help="File to upload for template creation")
    upload_filename = fields.Char('Upload Filename', help="Name of the uploaded file")
    compose_file = fields.Text('Compose File', 
                              help="Docker Compose file content when using the editor build method (deprecated, use fileContent)",
                              compute='_compute_compose_file',
                              inverse='_inverse_compose_file',
                              store=True)
    
    # Additional Info
    app_template_variables = fields.Text('App Template Variables', help="Variables for app template deployments")
    
    # Custom Template Additional Fields from Portainer
    project_path = fields.Char('Project Path', help="Path to the project inside the repository")
    entry_point = fields.Char('Entry Point', help="Docker compose file name inside the project path")
    created_by_user_id = fields.Integer('Created By User ID', help="ID of the user who created the template in Portainer")
    registry_url = fields.Char('Registry URL', help="URL of the registry for the template")
    
    # Useful computed fields for display
    get_formatted_env = fields.Text('Formatted Environment Variables', compute='_compute_formatted_env')
    get_formatted_volumes = fields.Text('Formatted Volumes', compute='_compute_formatted_volumes')
    get_formatted_ports = fields.Text('Formatted Ports', compute='_compute_formatted_ports')
    
    # Related stacks count
    stack_count = fields.Integer('Stack Count', compute='_compute_stack_count')
    
    # SQL Constraint to ensure Template ID is unique within a server
    _sql_constraints = [
        ('template_id_server_unique', 'UNIQUE(server_id, template_id)', 'Template ID must be unique within the same Portainer server!'),
    ]
    
    @api.constrains('template_id')
    def _check_template_id(self):
        """Additional validation for template_id to handle edge cases"""
        for template in self:
            if template.template_id:
                # Check for duplicate template IDs within the same server
                domain = [
                    ('server_id', '=', template.server_id.id),
                    ('template_id', '=', template.template_id),
                    ('id', '!=', template.id)  # exclude current record
                ]
                if self.search_count(domain) > 0:
                    raise ValidationError(_("Template ID %s already exists for this Portainer server!") % template.template_id)
    
    def _default_server_id(self):
        """Return default server if only one exists"""
        servers = self.env['j_portainer.server'].search([])
        if len(servers) == 1:
            return servers.id
        return False

    def _default_environment_id(self):
        """Return default environment if only one exists"""
        environments = self.env['j_portainer.environment'].search([])
        if len(environments) == 1:
            return environments.id
        return False

    @api.constrains('description', 'fileContent', 'upload_file', 'git_repository_url', 'build_method')
    def _check_required_fields(self):
        """Validate required fields based on build method"""
        for template in self:
            # Description is always required
            if not template.description:
                raise ValidationError(_("Description is required for all custom templates."))
            
            # Web Editor: File Content is required
            if template.build_method == 'editor' and not template.fileContent:
                raise ValidationError(_("File Content is required when Build Method is Web Editor."))
            
            # File Upload: Upload File is required
            if template.build_method == 'file' and not template.upload_file:
                raise ValidationError(_("Upload File is required when Build Method is File Upload."))
            
            # Git Repository: Repository URL is required
            if template.build_method == 'repository' and not template.git_repository_url:
                raise ValidationError(_("Repository URL is required when Build Method is Git Repository."))

    @api.onchange('build_method')
    def _onchange_build_method(self):
        """Clear fields when build method changes"""
        if self.build_method == 'editor':
            # Clear repository and file upload fields
            self.git_repository_url = False
            self.git_repository_reference = False
            self.git_compose_path = 'docker-compose.yml'  # Reset to default
            self.git_skip_tls = False
            self.git_authentication = False
            self.git_credentials_id = False
            self.git_username = False
            self.git_token = False
            self.git_save_credential = False
            self.git_credential_name = False
            self.upload_file = False
            self.upload_filename = False
            
        elif self.build_method == 'file':
            # Clear repository and editor fields
            self.git_repository_url = False
            self.git_repository_reference = False
            self.git_compose_path = 'docker-compose.yml'  # Reset to default
            self.git_skip_tls = False
            self.git_authentication = False
            self.git_credentials_id = False
            self.git_username = False
            self.git_token = False
            self.git_save_credential = False
            self.git_credential_name = False
            self.fileContent = False
            
        elif self.build_method == 'repository':
            # Clear editor and file upload fields
            self.fileContent = False
            self.upload_file = False
            self.upload_filename = False
    
    # The formatting functions for environment variables, volumes, and
    # categories are now inherited from j_portainer.template.mixin
    
    @api.depends('fileContent')
    def _compute_compose_file(self):
        """Copy content from fileContent to compose_file field for backward compatibility"""
        for template in self:
            template.compose_file = template.fileContent
            
    def _inverse_compose_file(self):
        """Copy content from compose_file to fileContent field for backward compatibility"""
        for template in self:
            template.fileContent = template.compose_file
    
    def _compute_stack_count(self):
        """Compute number of stacks created from this template"""
        for template in self:
            template.stack_count = self.env['j_portainer.stack'].search_count([
                ('custom_template_id', '=', template.id)
            ])
            
    # The ports formatting function is now inherited from j_portainer.template.mixin
    
    def action_refresh(self):
        """Refresh this specific custom template from Portainer"""
        self.ensure_one()
        
        if not self.server_id:
            raise UserError(_("Server is required to refresh custom template"))
            
        if not self.template_id:
            raise UserError(_("Template ID is required to refresh custom template"))
        
        try:
            _logger.info(f"Refreshing custom template '{self.title}' (ID: {self.template_id})")
            
            # Get the specific template from Portainer
            template_response = self.server_id._make_api_request(
                f'/api/custom_templates/{self.template_id}', 
                'GET',
                environment_id=self.environment_id.environment_id if self.environment_id else None
            )
            
            if template_response.status_code != 200:
                raise UserError(_("Failed to fetch template: %s") % template_response.text)
                
            # Parse the template data
            template_data = template_response.json()
            
            # Prepare update values
            update_vals = {
                'title': template_data.get('Title', self.title),
                'description': template_data.get('Description', ''),
                'note': template_data.get('Note', ''),
                'platform': 'linux' if str(template_data.get('Platform', 1)) == '1' else 'windows',
                'logo': template_data.get('Logo', ''),
                'categories': ','.join(template_data.get('Categories', [])),
            }
            
            # Handle type (convert integer to string if needed)
            template_type = template_data.get('Type', 1)
            if isinstance(template_type, int):
                template_type = str(template_type)
            update_vals['template_type'] = template_type
            
            # Also get file content if build method is editor
            if self.build_method == 'editor' or not self.fileContent:
                # Get the template file content
                file_response = self.server_id._make_api_request(
                    f'/api/custom_templates/{self.template_id}/file', 
                    'GET',
                    environment_id=self.environment_id.environment_id if self.environment_id else None
                )
                
                if file_response.status_code == 200:
                    file_data = file_response.json()
                    compose_content = None
                    
                    # Try different possible field names for the file content
                    for field_name in ['FileContent', 'StackFileContent', 'Content', 'stackFileContent']:
                        if field_name in file_data:
                            compose_content = file_data[field_name]
                            _logger.info(f"Retrieved file content (field: {field_name}). Content length: {len(compose_content)} chars")
                            break
                    
                    if compose_content:
                        update_vals.update({
                            'fileContent': compose_content,
                            'compose_file': compose_content,
                            'build_method': 'editor'
                        })
            
            # Update the template
            self.write(update_vals)
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Template Refreshed'),
                    'message': _("Custom template '%s' has been refreshed from Portainer") % self.title,
                    'sticky': False,
                }
            }
                
        except Exception as e:
            _logger.error(f"Error refreshing custom template {self.template_id}: {str(e)}")
            raise UserError(_("Error refreshing template: %s") % str(e))
        
    def action_refresh_file_content(self):
        """Refresh file content for this template from Portainer"""
        self.ensure_one()
        
        if not self.server_id:
            raise UserError(_("Server is required to refresh file content"))
            
        if not self.template_id:
            raise UserError(_("Template ID is required to refresh file content"))
            
        try:
            _logger.info(f"Fetching file content for template '{self.title}' (ID: {self.template_id})")
            file_response = self.server_id._make_api_request(f'/api/custom_templates/{self.template_id}/file', 'GET')
            
            if file_response.status_code == 200:
                file_data = file_response.json()
                compose_content = None
                
                # Try different possible field names for the file content
                for field_name in ['FileContent', 'StackFileContent', 'Content', 'stackFileContent']:
                    if field_name in file_data:
                        compose_content = file_data[field_name]
                        _logger.info(f"Retrieved file content (field: {field_name}) for template '{self.title}'. Content length: {len(compose_content)} chars")
                        break
                
                if compose_content:
                    self.write({
                        'fileContent': compose_content,
                        'compose_file': compose_content,
                        'build_method': 'editor'
                    })
                    
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('File Content Updated'),
                            'message': _("Template file content has been updated from Portainer"),
                            'sticky': False,
                            'type': 'success',
                        }
                    }
                else:
                    _logger.warning(f"No file content found in response for template {self.template_id}: {file_data}")
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('No File Content Found'),
                            'message': _("No file content was found for this template in Portainer"),
                            'sticky': False,
                            'type': 'warning',
                        }
                    }
            else:
                error_message = file_response.text
                _logger.warning(f"Failed to get file content for template {self.template_id}: {file_response.status_code} - {error_message}")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Error'),
                        'message': _("Failed to get file content: %s") % error_message,
                        'sticky': True,
                        'type': 'danger',
                    }
                }
        except Exception as e:
            _logger.error(f"Error fetching file content for template {self.template_id}: {str(e)}")
            raise UserError(_("Error fetching file content: %s") % str(e))
    
    def remove_custom_template(self):
        """Remove this custom template from both Portainer and Odoo"""
        self.ensure_one()
        
        # Store template title for messages before potentially unlinking record
        template_title = self.title
        template_id = self.template_id
        server_id = self.server_id
        
        # Check that the server is connected
        if server_id.status != 'connected':
            raise UserError(_("Cannot remove template: Server is not connected"))
            
        if not template_id:
            # If no template_id, just remove from Odoo without contacting Portainer
            self.unlink()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Template Removed'),
                    'message': _("Custom template '%s' has been removed from Odoo (no Portainer ID)") % template_title,
                    'sticky': False,
                    'next': {'type': 'ir.actions.act_window_close'}
                }
            }
            
        try:
            # Call the API to remove the template from Portainer
            api = self.env['j_portainer.api']
            result = api.template_action(server_id.id, template_id, 'delete')
            
            # Check for errors in the result - be very explicit about this check
            if isinstance(result, dict) and result.get('error'):
                error_message = result.get('error')
                _logger.error(f"Failed to remove template {template_title} from Portainer: {error_message}")
                
                # Only remove from Odoo if specifically requested with force_remove
                if self.env.context.get('force_remove', False):
                    self.unlink()
                    self.env.cr.commit()
                    
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Template Removed from Odoo Only'),
                            'message': _("Custom template '%s' could not be removed from Portainer but was removed from Odoo: %s") % (template_title, error_message),
                            'sticky': False,
                            'type': 'warning',
                            'next': {'type': 'ir.actions.act_window_close'}
                        }
                    }
                else:
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Error'),
                            'message': _("Failed to remove custom template from Portainer: %s. Template remains in Odoo.") % error_message,
                            'sticky': True,
                            'type': 'danger',
                        }
                    }
            
            # Only consider it a success if result is a dict with success=True
            # or if result is True (for backward compatibility)
            if (isinstance(result, dict) and result.get('success')) or result is True:
                # Log successful Portainer deletion
                _logger.info(f"Custom template {template_title} (ID: {template_id}) removed from Portainer")
                
                message = {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Template Removed'),
                        'message': _("Custom template '%s' has been removed from both Portainer and Odoo") % template_title,
                        'sticky': False,
                        'type': 'success',
                    }
                }
                
                # Now unlink the record from Odoo
                self.unlink()
                # Commit the transaction - important!
                self.env.cr.commit()
                
                return message
            else:
                # If result is not explicitly an error but also not a success
                _logger.error(f"Unexpected result when removing template {template_title} from Portainer: {result}")
                
                # Only remove from Odoo if specifically requested with force_remove
                if self.env.context.get('force_remove', False):
                    self.unlink()
                    self.env.cr.commit()
                    
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Template Removed from Odoo Only'),
                            'message': _("Custom template '%s' could not be removed from Portainer (unexpected response) but was removed from Odoo") % template_title,
                            'sticky': False,
                            'type': 'warning',
                            'next': {'type': 'ir.actions.act_window_close'}
                        }
                    }
                else:
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Error'),
                            'message': _("Failed to remove custom template from Portainer - unexpected response. Template remains in Odoo."),
                            'sticky': True,
                            'type': 'danger',
                        }
                    }
        except Exception as e:
            _logger.error(f"Error removing custom template: {str(e)}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _("Error removing template: %s") % str(e),
                    'sticky': True,
                    'type': 'danger',
                }
            }
        
    def force_remove_from_odoo(self):
        """Force remove custom template from Odoo regardless of Portainer status"""
        self.ensure_one()
        
        # Store template title for messages before potentially unlinking record
        template_title = self.title
        
        try:
            # Directly unlink the record from Odoo
            self.unlink()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Template Removed'),
                    'message': _("Custom template '%s' has been forcibly removed from Odoo only") % template_title,
                    'sticky': False,
                    'next': {'type': 'ir.actions.act_window_close'}
                }
            }
        except Exception as e:
            _logger.error(f"Error force removing custom template: {str(e)}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _("Error removing template from Odoo: %s") % str(e),
                    'sticky': True,
                    'type': 'danger',
                }
            }
    
    def action_deploy(self):
        """Open the deploy wizard for this template"""
        self.ensure_one()
        
        # Check that the server is connected
        if self.server_id.status != 'connected':
            raise UserError(_("Cannot deploy template: Server is not connected"))
            

        
        # Open the deployment wizard
        return {
            'name': _('Deploy Custom Template'),
            'type': 'ir.actions.act_window',
            'res_model': 'j_portainer.template.deploy.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_server_id': self.server_id.id,
                'default_custom_template_id': self.id,
                'default_is_custom': True,
                'default_template_title': self.title,
                'default_template_type': self.template_type,
                'default_name': self.title,
            }
        }
        
    def action_create_in_portainer(self):
        """Create this template in Portainer using the file upload API endpoint"""
        self.ensure_one()
        import requests
        import json

        if not self.server_id:
            raise UserError(_("Server is required for template creation"))
            
        if not self.environment_id:
            raise UserError(_("Environment is required for template creation"))
            
        # Get server details
        server = self.server_id
        portainer_env_id = self.environment_id.environment_id
        
        # Prepare the endpoint URL
        url = f"{server.url.rstrip('/')}/api/custom_templates/create/file?environment={portainer_env_id}"
        
        # Prepare headers with API key
        headers = {
            "X-API-Key": server._get_api_key_header()
        }
        
        # Convert platform and type to integer format as expected by Portainer
        platform_int = 1  # Default to Linux (1)
        if self.platform:
            platform_map = {
                'linux': 1,
                'windows': 2
            }
            platform_int = platform_map.get(self.platform.lower(), 1)
            
        # Convert template type to proper format
        type_str = self.template_type  # Default use as-is (should be "1", "2", or "3")
            
        # Prepare form data
        data = {
            "Title": self.title,
            "Description": self.description or f"Auto-created from Odoo",
            "Note": self.note or "Created from Odoo j_portainer module",
            "Platform": str(platform_int),  # Must be a string for multipart form
            "Type": type_str,              # "1" for Standalone/Podman, "2" for Swarm
            "Logo": self.logo or "",
            "Variables": "[]",  # Always send empty array to prevent null errors
            "AdministratorsOnly": "true"  # Match Portainer's default behavior
        }
        
        # Add categories if available
        if self.categories:
            try:
                # Try to format categories as JSON string
                categories = self.categories.split(",") if isinstance(self.categories, str) else []
                data["Categories"] = json.dumps(categories)
            except Exception as e:
                _logger.warning(f"Error formatting categories: {str(e)}")
        
        # Prepare the file content
        file_content = self.fileContent or self.compose_file or ""
        if not file_content:
            raise UserError(_("Template file content is required"))
            
        # Prepare the file for upload
        files = {
            "File": ("template.yml", file_content.encode('utf-8'), "text/x-yaml")
        }
        
        # Prepare API log data
        from datetime import datetime
        start_time = datetime.now()
        
        # Create log data for request
        log_vals = {
            'server_id': server.id,
            'endpoint': f'/api/custom_templates/create/file?environment={portainer_env_id}',
            'method': 'POST',
            'environment_id': portainer_env_id,
            'environment_name': self.environment_id.name if self.environment_id else '',
            'request_date': start_time,
            'request_data': json.dumps({
                'url': url,
                'method': 'POST',
                'body': data,
                'has_files': bool(files)
            }, indent=2)
        }
        
        try:
            _logger.info(f"Creating template in Portainer at URL: {url}")
            _logger.info(f"Template data: {data}")
            
            # Make the request with SSL verification as configured in server
            response = requests.post(
                url, 
                headers=headers,
                data=data,
                files=files,
                verify=server.verify_ssl
            )
            
            # Calculate response time
            end_time = datetime.now()
            response_time_ms = int((end_time - start_time).total_seconds() * 1000)
            
            # Prepare response log data
            response_log_data = {
                'status_code': response.status_code,
                'headers': dict(response.headers),
                'url': response.url
            }
            
            # Add response body
            try:
                if response.status_code in [204, 304]:
                    response_log_data['body'] = f"Empty response body (status {response.status_code})"
                else:
                    try:
                        response_json = response.json()
                        response_log_data['body'] = response_json
                    except Exception:
                        response_text = response.text[:5000] if response.text else ""
                        response_log_data['body'] = response_text
            except Exception as e:
                response_log_data['body'] = f"Error formatting response: {str(e)}"
            
            # Update log with response data
            log_vals.update({
                'status_code': response.status_code,
                'response_time_ms': response_time_ms,
                'response_data': json.dumps(response_log_data, indent=2),
                'error_message': json.dumps(response_log_data, indent=2) if response.status_code >= 300 else None,
            })
            
            # Create API log record
            self.env['j_portainer.api_log'].sudo().create(log_vals)
            
            # Check response
            if response.status_code in [200, 201, 202, 204]:
                try:
                    result = response.json()
                    template_id = result.get('Id', result.get('id'))
                    
                    if template_id:
                        # Update template ID in Odoo - skip write method to avoid triggering sync
                        self.with_context(skip_portainer_update=True).write({'template_id': template_id})
                        
                        return {
                            'type': 'ir.actions.client',
                            'tag': 'display_notification',
                            'params': {
                                'title': _('Template Created'),
                                'message': _('Template created successfully in Portainer with ID: %s') % template_id,
                                'sticky': False,
                                'type': 'success',
                            }
                        }
                    else:
                        # Success but no ID returned
                        return {
                            'type': 'ir.actions.client',
                            'tag': 'display_notification',
                            'params': {
                                'title': _('Template Created'),
                                'message': _('Template created successfully in Portainer, but no ID was returned'),
                                'sticky': False,
                                'type': 'success',
                            }
                        }
                except Exception as e:
                    # Success but couldn't parse JSON
                    _logger.warning(f"Couldn't parse JSON response: {str(e)}")
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Template Created'),
                            'message': _('Template created successfully in Portainer (status: %s)') % response.status_code,
                            'sticky': False,
                            'type': 'success',
                        }
                    }
            else:
                # Error response
                error_message = response.text
                try:
                    error_data = response.json()
                    if isinstance(error_data, dict) and 'message' in error_data:
                        error_message = error_data['message']
                except Exception:
                    pass
                
                raise UserError(_("Error creating template in Portainer: %s (status: %s)") % (
                    error_message, response.status_code))
                
        except requests.exceptions.RequestException as e:
            # Log the connection error
            end_time = datetime.now()
            response_time_ms = int((end_time - start_time).total_seconds() * 1000)
            
            error_data = {
                'error_type': 'RequestException',
                'url': url,
                'method': 'POST',
                'message': str(e)
            }
            
            log_vals.update({
                'status_code': 0,
                'response_time_ms': response_time_ms,
                'error_message': json.dumps(error_data, indent=2),
                'response_data': json.dumps(error_data, indent=2)
            })
            
            # Create API log record for the error
            self.env['j_portainer.api_log'].sudo().create(log_vals)
            
            raise UserError(_("Error connecting to Portainer: %s") % str(e))
        
    def _sync_to_portainer(self, vals=None, method='post'):
        """
        Synchronize template with Portainer via direct API calls
        
        @param vals: Values dictionary for the template (used for creation)
        @param method: HTTP method to use (post for create, put for update)
        @return: Response from Portainer API or None if failed
        """
        # Make sure json module is explicitly available in this method
        import json
        self.ensure_one()
        
        # Use passed vals or prepare from current record for updates
        if method == 'post' and vals:
            server_id = vals.get('server_id')
            environment_id = vals.get('environment_id')
            template_data = self._prepare_template_data(vals)
        else:
            server_id = self.server_id.id
            environment_id = self.environment_id.id if self.environment_id else None
            
            # Map the environment ID correctly if using a direct Portainer environment ID
            # This fixes the "foreign key constraint" error in the template sync
            if isinstance(environment_id, (int, str)) and not self.env['j_portainer.environment'].browse(environment_id).exists():
                # Try to find a matching environment by Portainer environment_id
                portainer_env_id = environment_id
                matching_env = self.env['j_portainer.environment'].search([
                    ('server_id', '=', server_id), 
                    ('environment_id', '=', portainer_env_id)
                ], limit=1)
                
                if matching_env:
                    environment_id = matching_env.id
                    _logger.info(f"Mapped Portainer environment ID {portainer_env_id} to Odoo environment record ID {environment_id}")
                elif self.server_id.environment_ids:
                    # Fallback to first environment for this server
                    environment_id = self.server_id.environment_ids[0].id
                    _logger.warning(f"Using first environment {environment_id} as fallback for Portainer environment ID {portainer_env_id}")
            template_data = self._prepare_template_data_from_record()
            
        if not server_id or not environment_id:
            _logger.error("Cannot sync template: Server and Environment are required")
            return None
            
        api = self.env['j_portainer.api']
        server = self.env['j_portainer.server'].browse(server_id)
        
        # Ensure template_data has the right format for API
        # Add environment ID to ensure it's created in the right place
        if isinstance(template_data, dict) and environment_id:
            template_data['environment_id'] = environment_id
            
        _logger.info(f"Syncing template to Portainer using {method} method")
        
        # For updates, use the existing template ID
        template_id = None
        if method == 'put':
            template_id = self.template_id
            
        # Try multiple API endpoints and approaches
        response = None
        error_messages = []
        
        # Method 0: Direct multipart form upload (simple and reliable)
        if (method == 'post' or (method == 'put' and self.template_id)) and self.build_method == 'editor' and (self.fileContent or self.compose_file):
            try:
                # We need to get the Portainer environment ID, not the Odoo record ID
                env_record = self.env['j_portainer.environment'].browse(environment_id)
                portainer_env_id = env_record.environment_id if env_record else None
                
                server_info = self.env['j_portainer.server'].browse(server_id)
                server_url = server_info.url
                api_key = server_info.api_key
                
                if not portainer_env_id:
                    # Fallback to using first environment's ID
                    if server_info and server_info.environment_ids:
                        portainer_env_id = server_info.environment_ids[0].environment_id
                
                if not server_url or not api_key or not portainer_env_id:
                    _logger.warning("Missing server URL, API key, or environment ID for direct template upload")
                else:
                    # Prepare URL with endpoint
                    if server_url.endswith('/'):
                        server_url = server_url[:-1]
                    
                    # Use different endpoints for create vs update
                    if method == 'post':
                        # For new template creation with file, use the create/file endpoint
                        url = f"{server_url}/api/custom_templates/create/file"
                    else:
                        # For updates, include template ID in the URL with environment parameter
                        url = f"{server_url}/api/custom_templates/{template_id}"
                        if portainer_env_id:
                            url = f"{url}?environment={portainer_env_id}"
                    
                    # Prepare headers with authorization
                    headers = {'Authorization': f'Bearer {api_key}'}
                    
                    # Convert platform and template type to strings
                    platform_value = template_data.get('platform', 1)
                    type_value = template_data.get('type', 1)
                    
                    # Get file content (prefer fileContent)
                    file_content = self.fileContent or self.compose_file
                    
                    # Create data differently based on method
                    import requests
                    import json
                    
                    if method == 'post':
                        # For creation, use multipart form data as required by the API
                        # Prepare form data for multipart/form-data request
                        data = {
                            'Title': self.title,
                            'Description': self.description or f'Template for {self.title}',
                            'Note': self.note or '',
                            'Platform': str(platform_value),  # 1 for Linux, 2 for Windows
                            'Type': str(type_value),  # 1 for Standalone/Podman, 2 for Swarm
                            'Logo': self.logo or '',
                            'AdministratorsOnly': 'true'  # Match Portainer's default behavior
                        }
                        
                        # Add environment ID in the URL query params instead of form data
                        # This ensures compatibility with Portainer CE current API
                        if portainer_env_id:
                            url = f"{url}?environment={portainer_env_id}"
                        
                        # Add variables if available
                        if self.environment_variables:
                            try:
                                # Convert to proper JSON string if it's a raw string
                                if isinstance(self.environment_variables, str):
                                    # Try to parse as JSON to validate
                                    env_vars_json = json.loads(self.environment_variables)
                                    data['Variables'] = json.dumps(env_vars_json)
                                else:
                                    data['Variables'] = json.dumps(self.environment_variables)
                            except Exception as e:
                                _logger.warning(f"Error formatting environment variables: {str(e)}")
                                data['Variables'] = self.environment_variables
                                
                        # Add categories if available
                        if self.categories:
                            try:
                                # Try to format categories as JSON string
                                categories = self.categories.split(",") if isinstance(self.categories, str) else []
                                data["Categories"] = json.dumps(categories)
                            except Exception as e:
                                _logger.warning(f"Error formatting categories: {str(e)}")
                            
                        # Prepare files for upload - use a proper MIME type for YAML files
                        files = {
                            'File': ('template.yml', file_content.encode('utf-8'), 'text/x-yaml')
                        }
                        
                        # Log the complete request for debugging
                        _logger.info(f"POST Request URL: {url}")
                        _logger.info(f"POST Request Headers: {headers}")
                        _logger.info(f"POST Request Data: {data}")
                        _logger.info(f"POST Request Files: {list(files.keys())}")
                        
                        # Verify we have environment ID before proceeding
                        if 'environmentId' not in data:
                            _logger.warning("No environment ID found for template creation, trying to find one")
                            # Try one more attempt to find environment ID
                            server = self.env['j_portainer.server'].browse(server_id)
                            for env in server.environment_ids:
                                if env.environment_id:
                                    _logger.info(f"Found environment ID: {env.environment_id}")
                                    data['environmentId'] = str(env.environment_id)
                                    break
                        
                        # Send the POST request with SSL verification as configured in server
                        res = requests.post(url, headers=headers, data=data, files=files, verify=server_info.verify_ssl)
                    else:
                        # For updates, use application/json as required by the API
                        # Prepare JSON data
                        json_data = {
                            'Title': self.title,
                            'Description': self.description or f'Template for {self.title}',
                            'Note': self.note or '',
                            'Platform': int(platform_value),  # 1 or 2
                            'Type': int(type_value),  # 1, 2, or 3
                            'Logo': self.logo or '',
                        }
                        
                        # Add variables if available
                        if self.environment_variables:
                            try:
                                if isinstance(self.environment_variables, str):
                                    env_vars = json.loads(self.environment_variables)
                                    json_data['Variables'] = env_vars
                                else:
                                    json_data['Variables'] = self.environment_variables
                            except Exception as e:
                                _logger.warning(f"Failed to parse variables: {e}")
                                json_data['Variables'] = []
                        else:
                            json_data['Variables'] = []
                        
                        # Add categories if available
                        if self.categories:
                            try:
                                categories = self.categories.split(",") if isinstance(self.categories, str) else []
                                json_data['Categories'] = [cat.strip() for cat in categories if cat.strip()]
                            except Exception as e:
                                _logger.warning(f"Error formatting categories: {str(e)}")
                                json_data['Categories'] = []
                        else:
                            json_data['Categories'] = []
                        
                        # Add file content directly in the JSON payload - this is crucial for updates
                        if file_content:
                            json_data['FileContent'] = file_content
                        else:
                            _logger.warning("No file content available for template update")
                        
                        # Use X-API-Key header instead of Authorization Bearer for consistency
                        json_headers = {
                            'X-API-Key': api_key,
                            'Content-Type': 'application/json'
                        }
                        
                        # Log the complete request for debugging
                        _logger.info(f"PUT Request URL: {url}")
                        _logger.info(f"PUT Request Headers: {json_headers}")
                        _logger.info(f"PUT Request JSON: {json.dumps(json_data, indent=2)}")
                        
                        # Send the PUT request with SSL verification as configured in server
                        res = requests.put(url, headers=json_headers, json=json_data, verify=server_info.verify_ssl)
                    
                    if res.status_code in [200, 201, 202]:
                        try:
                            response_data = res.json()
                            if method == 'post':
                                _logger.info(f"Template created successfully via multipart form: {response_data}")
                                # If this was a creation and we got a new ID, store it
                                if response_data and ('Id' in response_data or 'id' in response_data):
                                    new_id = response_data.get('Id') or response_data.get('id')
                                    if new_id and not self.template_id:
                                        self.template_id = str(new_id)
                            else:
                                _logger.info(f"Template updated successfully via JSON API: {response_data}")
                            return response_data
                        except Exception as e:
                            # Handle non-JSON response
                            _logger.info(f"Successfully synchronized template, but response was not JSON: {e}")
                            return {'success': True, 'message': 'Template synchronized successfully'}
                    elif res.status_code == 404 and method == 'put':
                        # For 404 on PUT requests, try to create instead (template might have been deleted in Portainer)
                        _logger.warning(f"Template with ID {template_id} not found in Portainer, attempting to create a new one")
                        
                        # Switch to POST request to create a new template
                        create_url = f"{server_url}/api/custom_templates/create/file"
                        
                        # For creation after failed update, we need to use multipart form data format
                        # but we may not have the original 'data' and 'files' from the PUT request context
                        # so recreate the POST request data from the current record
                        
                        # Prepare form data for multipart/form-data request
                        post_data = {
                            'Title': self.title,
                            'Description': self.description or f'Template for {self.title}',
                            'Note': self.note or '',
                            'Platform': str(platform_value),  # 1 for Linux, 2 for Windows
                            'Type': str(type_value),  # 1 for Standalone/Podman, 2 for Swarm
                            'Logo': self.logo or '',
                        }
                        
                        # Add environment ID to the URL query params instead of form data
                        if portainer_env_id:
                            create_url = f"{create_url}?environment={portainer_env_id}"
                            
                        # Add variables if available
                        if self.environment_variables:
                            try:
                                # Convert to proper JSON string if it's a raw string
                                if isinstance(self.environment_variables, str):
                                    # Try to parse as JSON to validate
                                    env_vars_json = json.loads(self.environment_variables)
                                    post_data['Variables'] = json.dumps(env_vars_json)
                                else:
                                    post_data['Variables'] = json.dumps(self.environment_variables)
                            except Exception as e:
                                _logger.warning(f"Error formatting environment variables for fallback: {str(e)}")
                                post_data['Variables'] = self.environment_variables
                                
                        # Add categories if available
                        if self.categories:
                            try:
                                # Try to format categories as JSON string
                                categories = self.categories.split(",") if isinstance(self.categories, str) else []
                                post_data["Categories"] = json.dumps(categories)
                            except Exception as e:
                                _logger.warning(f"Error formatting categories for fallback: {str(e)}")
                            
                        # Prepare files for upload with proper MIME type
                        post_files = {
                            'File': ('template.yml', file_content.encode('utf-8'), 'text/x-yaml')
                        }
                        
                        _logger.info(f"Sending fallback multipart form POST request to {create_url}")
                        create_res = requests.post(url=create_url, headers=headers, data=post_data, files=post_files, verify=server_info.verify_ssl)
                        
                        if create_res.status_code in [200, 201, 202]:
                            try:
                                create_data = create_res.json()
                                _logger.info(f"Successfully created new template after 404 on update: {create_data}")
                                # Update template ID if we got a new one
                                if create_data and ('Id' in create_data or 'id' in create_data):
                                    new_id = create_data.get('Id') or create_data.get('id')
                                    if new_id:
                                        self.template_id = str(new_id)
                                return create_data
                            except Exception as e:
                                _logger.info(f"Created template successfully, but response was not JSON: {e}")
                                return {'success': True, 'message': 'New template created successfully after 404'}
                        else:
                            error_messages.append(f"Fallback creation after 404 failed: {create_res.status_code} - {create_res.text}")
                            _logger.warning(f"Fallback creation after 404 failed: {create_res.status_code} - {create_res.text}")
                    else:
                        # Log detailed error information
                        error_detail = f"HTTP {res.status_code}"
                        try:
                            error_json = res.json()
                            error_detail += f" - {json.dumps(error_json)}"
                        except:
                            error_detail += f" - {res.text}"
                            
                        error_messages.append(f"API request failed: {error_detail}")
                        _logger.warning(f"API request failed: {error_detail}")
            except Exception as e:
                error_messages.append(f"Direct multipart form failed: {str(e)}")
                _logger.warning(f"Direct multipart form failed: {str(e)}")
        
        # Method 1: Standard API endpoint
        try:
            if method == 'post':
                response = api.create_template(server_id, template_data)
            else:
                # Get the Portainer environment ID for logging
                env_record = self.env['j_portainer.environment'].browse(environment_id)
                portainer_env_id = env_record.environment_id if env_record else None
                response = api.update_template(server_id, template_id, template_data, environment_id=portainer_env_id)
                
                # Check if update failed with 404 (template not found) - try creating it instead
                if response and isinstance(response, dict) and response.get('error') and '404' in str(response.get('error')):
                    _logger.warning(f"Template ID {template_id} not found in Portainer. Attempting to create it instead.")
                    # Remove original template_id to allow Portainer to generate a new one
                    create_data = template_data.copy()
                    
                    # Try to create the template as a new one - explicitly use POST for creation
                    _logger.info(f"Switching to POST method for template creation after 404 error")
                    response = api.create_template(server_id, create_data)
                    
                    # If creation was successful, update the template_id in our database
                    if response and ('Id' in response or 'id' in response):
                        new_id = response.get('Id') or response.get('id')
                        if new_id:
                            _logger.info(f"Created new template with ID {new_id} to replace missing template {template_id}")
                            # Update the template_id in the database
                            self.template_id = str(new_id)
                
            if response and ('Id' in response or 'id' in response or 'success' in response):
                _logger.info(f"Template synced successfully via standard API: {response}")
                return response
        except Exception as e:
            error_messages.append(f"Standard API method failed: {str(e)}")
            _logger.warning(f"Standard API method failed: {str(e)}")
            
        # Method 1B: Direct environment API endpoint for custom templates
        try:
            # We need to get the Portainer environment ID, not the Odoo record ID
            # Find the environment record to get its environment_id field
            # Make sure json is imported for this scope
            import json
            
            env_record = self.env['j_portainer.environment'].browse(environment_id)
            portainer_env_id = env_record.environment_id if env_record else None
            
            if not portainer_env_id:
                # Fallback to using first environment's ID
                server = self.env['j_portainer.server'].browse(server_id)
                if server and server.environment_ids:
                    portainer_env_id = server.environment_ids[0].environment_id
            
            if not portainer_env_id:
                raise UserError(_("No valid environment found for custom template"))
                
            _logger.info(f"Using Portainer environment ID {portainer_env_id} for API call")
            
            # Try direct environment endpoint for custom templates
            env_endpoint = f"/custom_templates?environment={portainer_env_id}"
            
            if method == 'post':
                # For creation, always use POST
                response = api.direct_api_call(
                    server_id, 
                    endpoint=env_endpoint,
                    method='POST',  # Explicitly use POST for creation
                    data=template_data
                )
            else:
                env_endpoint = f"/custom_templates/{template_id}?environment={portainer_env_id}"
                # For PUT requests, ensure we're providing either fileContent or repository data
                update_data = template_data.copy()
                
                # Add fileContent for editor templates
                if self.build_method == 'editor':
                    # Prefer fileContent field, fall back to compose_file for backward compatibility
                    content = self.fileContent or self.compose_file
                    if content:
                        update_data['fileContent'] = content
                    # Delete composeFileContent if present to avoid confusion
                    if 'composeFileContent' in update_data:
                        del update_data['composeFileContent']
                
                # For Git repository templates, ensure repository info is present
                elif self.build_method == 'repository' and self.git_repository_url:
                    if 'repository' not in update_data:
                        update_data['repository'] = {
                            'url': self.git_repository_url,
                            'stackfile': self.git_compose_path or 'docker-compose.yml'
                        }
                        if self.git_repository_reference:
                            update_data['repository']['reference'] = self.git_repository_reference
                
                # Make sure to use json module imported at method level
                import json
                
                response = api.direct_api_call(
                    server_id, 
                    endpoint=env_endpoint,
                    method='PUT',
                    data=update_data
                )
                
            if response and ('Id' in response or 'id' in response or 'success' in response):
                _logger.info(f"Template synced successfully via environment API: {response}")
                return response
        except Exception as e:
            error_messages.append(f"Environment API method failed: {str(e)}")
            _logger.warning(f"Environment API method failed: {str(e)}")
            
        # Method 2: File import method for stack/compose templates
        if method == 'post' and ((vals and vals.get('build_method') == 'editor' and (vals.get('fileContent') or vals.get('compose_file'))) 
                                or (self.build_method == 'editor' and (self.fileContent or self.compose_file))):
            try:
                # Prefer fileContent field, fall back to compose_file for backward compatibility
                if vals:
                    compose_file = vals.get('fileContent') or vals.get('compose_file')
                else:
                    compose_file = self.fileContent or self.compose_file
                
                # Create file template structure
                file_template = {
                    "version": "2",
                    "templates": [
                        {
                            "type": int(template_data.get('type', 1)),
                            "title": template_data.get('title', 'Custom Template'),
                            "description": template_data.get('description', ''),
                            "note": template_data.get('note', False),
                            "platform": template_data.get('platform', 'linux'),
                            "categories": template_data.get('categories', ['Custom']),
                        }
                    ]
                }
                
                # For stack templates, add stack file content
                if int(template_data.get('type', 1)) == 2:
                    file_template['templates'][0]['stackfile'] = compose_file
                
                # Try regular template import
                file_response = api.import_template_file(server_id, file_template)
                
                if file_response and ('success' in file_response or 'Id' in file_response or 'id' in file_response):
                    _logger.info(f"Template created via file import: {file_response}")
                    return file_response
                    
                # If regular import fails, try with environment specified
                try:
                    # Get environment ID from portainer for this scope
                    try:
                        # Find the environment record to get its environment_id field
                        env_record = self.env['j_portainer.environment'].browse(environment_id)
                        env_portainer_id = env_record.environment_id if env_record else None
                        
                        if not env_portainer_id:
                            # Fallback to using first environment's ID
                            server = self.env['j_portainer.server'].browse(server_id)
                            if server and server.environment_ids:
                                env_portainer_id = server.environment_ids[0].environment_id
                        _logger.info(f"Using Portainer environment ID {env_portainer_id} for file upload")
                    except Exception as env_error:
                        _logger.warning(f"Could not resolve environment ID: {str(env_error)}")
                        env_portainer_id = 1  # Default to first environment ID
                    
                    # Try direct file upload to environment endpoint
                    # Make sure json module is available in this scope
                    import json
                    multipart_data = {
                        'file': json.dumps(file_template),
                        'type': template_data.get('type', 1),
                        'environment': env_portainer_id
                    }
                    
                    env_file_response = api.direct_api_call(
                        server_id,
                        endpoint="/api/custom_templates/file",
                        method='POST',
                        data=multipart_data,
                        headers={'Content-Type': 'multipart/form-data'},
                        use_multipart=True
                    )
                    
                    # Check if response is a dict or a response object
                    if isinstance(env_file_response, dict):
                        # Dict response from enhanced direct_api_call
                        if env_file_response.get('success') or 'Id' in env_file_response or 'id' in env_file_response:
                            _logger.info(f"Template created via environment file import: {env_file_response}")
                            return env_file_response
                    elif env_file_response and hasattr(env_file_response, 'status_code'):
                        # Response object
                        if env_file_response.status_code in [200, 201, 202, 204]:
                            try:
                                result = env_file_response.json()
                                _logger.info(f"Template created via environment file import with response object: {result}")
                                return result
                            except Exception:
                                # Handle non-JSON success response
                                return {'success': True, 'message': 'Template created successfully via file import'}
                except Exception as e2:
                    error_messages.append(f"Environment file import method failed: {str(e2)}")
                    _logger.warning(f"Environment file import method failed: {str(e2)}")
            except Exception as e:
                error_messages.append(f"File import method failed: {str(e)}")
                _logger.warning(f"File import method failed: {str(e)}")
        
        # If we get here, all methods failed
        error_summary = "; ".join(error_messages)
        _logger.error(f"All Portainer synchronization methods failed: {error_summary}")
        
        # Return failure
        return None
        
    def copy(self, default=None):
        """Override copy method to clear raw data fields in duplicated templates"""
        if default is None:
            default = {}
            
        # Explicitly clear raw data fields
        default.update({
            'fileContent': None,
            'compose_file': None,
            'environment_variables': None,
            'volumes': None,
            'ports': None,
            'repository': None,
        })
        
        # Add "(copy)" to title if not already specified
        if 'title' not in default:
            default['title'] = _("%s (copy)") % self.title
            
        # Use standard method to copy the record with our defaults
        return super(PortainerCustomTemplate, self).copy(default)
    
    # def _create_template_in_portainer(self):
    #     """Create this template in Portainer using the server's API request method"""
    #     self.ensure_one()
        
    #     if not self.server_id:
    #         raise UserError(_("Server is required for template creation"))
            
    #     if not self.environment_id:
    #         raise UserError(_("Environment is required for template creation"))
        
    #     # Get server details
    #     server = self.server_id
    #     portainer_env_id = self.environment_id.environment_id
        
    #     # Convert platform and type to integer format as expected by Portainer
    #     platform_int = 1  # Default to Linux (1)
    #     if self.platform:
    #         platform_map = {
    #             'linux': 1,
    #             'windows': 2
    #         }
    #         platform_int = platform_map.get(self.platform.lower(), 1)
            
    #     # Prepare form data
    #     data = {
    #         "Title": self.title,
    #         "Description": self.description or f"Auto-created from Odoo",
    #         "Note": self.note or "Created from Odoo j_portainer module",
    #         "Platform": str(platform_int),  # Must be a string for multipart form
    #         "Type": self.template_type,   # Already a string in our model
    #         "Logo": self.logo or "",
    #         "Variables": self.environment_variables or "[]"
    #     }
        
    #     # Add categories if provided
    #     if self.categories:
    #         data["Categories"] = self.categories
        
    #     # Add method-specific data and files
    #     files = None
        
    #     if self.build_method == 'editor':
    #         # Web editor method - check for file content in fileContent or compose_file
    #         file_content = self.fileContent or self.compose_file
    #         if not file_content:
    #             raise UserError(_("File content is required when using Web Editor build method. Please provide content in the File Content field."))
            
    #         files = {
    #             'file': ('docker-compose.yml', file_content.encode('utf-8'), 'text/plain')
    #         }
    #     elif self.build_method == 'file' and self.upload_file:
    #         # File upload method
    #         import base64
    #         file_data = base64.b64decode(self.upload_file)
    #         filename = self.upload_filename or 'docker-compose.yml'
    #         files = {
    #             'file': (filename, file_data, 'application/octet-stream')
    #         }
    #     elif self.build_method == 'repository':
    #         # Git repository method
    #         data.update({
    #             "RepositoryURL": self.git_repository_url,
    #             "RepositoryReference": self.git_repository_reference or "refs/heads/master",
    #             "ComposeFilePathInRepository": self.git_compose_path or "docker-compose.yml",
    #             "RepositorySkipTLSVerify": str(self.git_skip_tls).lower(),
    #         })
            
    #         # Add authentication if enabled
    #         if self.git_authentication:
    #             if self.git_credentials_id:
    #                 data["RepositoryGitCredentialID"] = str(self.git_credentials_id.credential_id)
    #             elif self.git_username and self.git_token:
    #                 data.update({
    #                     "RepositoryUsername": self.git_username,
    #                     "RepositoryPassword": self.git_token,
    #                 })
                    
    #                 # Save credentials if requested
    #                 if self.git_save_credential and self.git_credential_name:
    #                     data.update({
    #                         "SaveCredential": "true",
    #                         "CredentialName": self.git_credential_name,
    #                     })
        
    #     # Debug: Log the data being sent to help diagnose issues
    #     _logger.info(f"Creating template with data: {data}")
    #     _logger.info(f"Build method: {self.build_method}")
    #     _logger.info(f"Has files: {bool(files)}")
    #     if files:
    #         _logger.info(f"Files keys: {list(files.keys())}")
        
    #     # Make API request using server's method for proper logging
    #     if files:
    #         # For multipart requests with files, we need to use the multipart mode
    #         # and include file data in the data parameter
    #         import requests
            
    #         # Make direct request for file uploads since _make_api_request doesn't support files parameter
    #         url = f"{server.url.rstrip('/')}/api/custom_templates/create/file?environment={portainer_env_id}"
    #         headers = {
    #             "X-API-Key": server._get_api_key_header()
    #         }
            
    #         _logger.info(f"Making file upload request to: {url}")
    #         response = requests.post(
    #             url,
    #             headers=headers,
    #             data=data,
    #             files=files,
    #             verify=server.verify_ssl,
    #             timeout=30
    #         )
    #     else:
    #         # For non-file requests, use the server's API request method
    #         _logger.info(f"Making non-file request")
    #         response = server._make_api_request(
    #             f'/api/custom_templates/create/file?environment={portainer_env_id}',
    #             'POST',
    #             data=data,
    #             use_multipart=True
    #         )
        
    #     if response.status_code in [200, 201]:
    #         try:
    #             result = response.json()
    #             template_id = result.get('Id', result.get('id'))
                
    #             if template_id:
    #                 # Update template ID in Odoo
    #                 self.write({'template_id': template_id, 'details': result, 'last_sync': fields.Datetime.now()})
    #                 _logger.info(f"Template created successfully in Portainer with ID: {template_id}")
    #                 return True
    #         except Exception as e:
    #             _logger.warning(f"Couldn't parse JSON response: {str(e)}")
    #             return True  # Still consider success if we got 200/201
    #     else:
    #         # Get detailed error message
    #         error_message = response.text
    #         try:
    #             error_data = response.json()
    #             if isinstance(error_data, dict) and 'message' in error_data:
    #                 error_message = error_data['message']
    #         except Exception:
    #             pass
            
    #         _logger.error(f"Error creating template in Portainer: {error_message} (status: {response.status_code})")
    #         raise UserError(_("Failed to create template in Portainer: %s (Status: %s)") % (error_message, response.status_code))

    @api.model
    def create(self, vals):
        """Create custom template in Odoo and automatically post to Portainer"""
        # Check required fields
        if not vals.get('server_id'):
            raise UserError(_("Server is required for custom templates"))
        if not vals.get('environment_id'):
            raise UserError(_("Environment is required for custom templates"))
        
        # If manual template ID is provided, use it
        if vals.get('manual_template_id'):
            _logger.info(f"Using manually provided template ID: {vals.get('manual_template_id')}")
            vals['template_id'] = vals.get('manual_template_id')
        
        # Create the record in Odoo
        record = super(PortainerCustomTemplate, self).create(vals)
        
        # Skip Portainer creation if:
        # 1. skip_portainer_create flag is set (used during sync operations)
        # 2. template_id already exists (indicates this is a sync from server)
        # 3. manual_template_id was provided (user manually specified existing template)
        if vals.get('skip_portainer_create') or vals.get('template_id') or vals.get('manual_template_id'):
            return record
            
        # Auto-create in Portainer using the separated method
        # If this fails, it will raise UserError and prevent record creation
        record.action_create_in_portainer()

        return record
        
    def write(self, vals):
        """Override write to sync with Portainer"""
        # Skip Portainer update if we're just updating from a sync operation or creation
        if (self.env.context.get('skip_portainer_update') or 
            self.env.context.get('skip_portainer_create') or
            self.env.context.get('from_sync')):
            return super(PortainerCustomTemplate, self).write(vals)
        
        # Update in Odoo first
        result = super(PortainerCustomTemplate, self).write(vals)
        
        # Then sync to Portainer
        for template in self:
            if template.template_id and template.server_id.status == 'connected':
                # Skip if we're just setting internal flags
                if len(vals) == 1 and ('skip_portainer_create' in vals or 'last_sync' in vals):
                    continue
                
                try:
                    response = template._sync_to_portainer(vals, method='put')
                    if not response:
                        raise UserError(_("Failed to update template in Portainer. Changes not saved."))
                except Exception as e:
                    raise UserError(_("Error updating template in Portainer: %s") % str(e))
        
        return result
    
    def _prepare_template_data(self, vals):
        """Prepare template data for Portainer API v2 from vals dictionary"""
        # Make sure json module is available in this method 
        import json
        
        # Set required fields with fallbacks if empty
        title = vals.get('title') or 'Custom Template'
        description = vals.get('description') or f'Template for {title}'
        
        # Convert platform string to integer for Portainer v2 API
        platform_value = vals.get('platform', 'linux')
        platform_int = 1  # Default to Linux (1)
        if platform_value:
            platform_map = {
                'linux': 1,
                'windows': 2
            }
            platform_int = platform_map.get(platform_value.lower(), 1)
            
        # Prepare primary fields based on v2 API requirements
        template_data = {
            'type': int(vals.get('template_type', 1)),
            'title': title,
            'description': description,
            'note': vals.get('note', ''),
            'platform': platform_int,
            'logo': vals.get('logo', '')
        }
        
        # Handle categories - ensure proper format for v2 API
        category_list = []
        if vals.get('categories'):
            if isinstance(vals.get('categories'), str):
                # Convert comma-separated string to list
                category_list = [c.strip() for c in vals.get('categories').split(',') if c.strip()]
            elif isinstance(vals.get('categories'), list):
                category_list = vals.get('categories')
                
        # Ensure at least one category exists
        if not category_list:
            category_list = ['Custom']
            
        template_data['categories'] = category_list
        
        # Handle environment variables if specified - ensure proper format for v2 API
        if vals.get('environment_variables'):
            try:
                env_vars = json.loads(vals.get('environment_variables')) if isinstance(vals.get('environment_variables'), str) else vals.get('environment_variables')
                if isinstance(env_vars, list):
                    # Validate each environment variable has required fields
                    valid_env_vars = []
                    for env in env_vars:
                        if isinstance(env, dict) and 'name' in env:
                            valid_env_vars.append(env)
                    template_data['env'] = valid_env_vars
            except Exception as e:
                _logger.warning(f"Error parsing environment variables: {str(e)}")
        
        # Handle volumes if specified
        if vals.get('volumes'):
            try:
                volumes = json.loads(vals.get('volumes')) if isinstance(vals.get('volumes'), str) else vals.get('volumes')
                template_data['volumes'] = volumes
            except Exception as e:
                _logger.warning(f"Error parsing volumes: {str(e)}")
                
        # Handle ports if specified
        if vals.get('ports'):
            try:
                ports = json.loads(vals.get('ports')) if isinstance(vals.get('ports'), str) else vals.get('ports')
                template_data['ports'] = ports
            except Exception as e:
                _logger.warning(f"Error parsing ports: {str(e)}")
        
        # Add image for container templates (type 1)
        if template_data['type'] == 1 and vals.get('image'):
            template_data['image'] = vals.get('image')
            
            # Add registry if specified
            if vals.get('registry'):
                template_data['registry'] = vals.get('registry')
        
        # Handle build method for templates
        build_method = vals.get('build_method')
        
        # Include fileContent for all template types if using editor method
        if build_method == 'editor':
            # Web editor method - always add fileContent for Portainer API v2
            # Prefer fileContent field, fall back to compose_file for backward compatibility
            compose_content = vals.get('fileContent', '') or vals.get('compose_file', '')
            if compose_content:
                template_data['fileContent'] = compose_content
                _logger.info(f"Including file content in template data. Length: {len(compose_content)} chars")
        
        # Repository method specific settings
        if build_method == 'repository':
                # Git repository method
                repository_data = {
                    'url': vals.get('git_repository_url', ''),
                    'stackfile': vals.get('git_compose_path', 'docker-compose.yml')
                }
                
                # Add reference if specified - use referenceName for v2 API
                if vals.get('git_repository_reference'):
                    repository_data['referenceName'] = vals.get('git_repository_reference')
                    
                template_data['repository'] = repository_data
                
                # Handle authentication if needed
                if vals.get('git_authentication'):
                    template_data['repositoryAuthentication'] = True
                    
                    # Use Git credentials if specified
                    if vals.get('git_credentials_id'):
                        credentials = self.env['j_portainer.git.credentials'].browse(vals.get('git_credentials_id'))
                        if credentials:
                            template_data['repositoryUsername'] = credentials.username
                            template_data['repositoryPassword'] = credentials.password
                    else:
                        # Otherwise use username/token from form
                        template_data['repositoryUsername'] = vals.get('git_username', '')
                        template_data['repositoryPassword'] = vals.get('git_token', '')
        
        return template_data
        
    def _prepare_template_data_from_record(self):
        """Prepare template data for Portainer API v2 from current record"""
        # Make sure json module is available in this method scope
        import json
        
        self.ensure_one()
        
        # Convert platform string to integer for Portainer v2 API
        platform_int = 1  # Default to Linux (1)
        if self.platform:
            platform_map = {
                'linux': 1,
                'windows': 2
            }
            platform_int = platform_map.get(self.platform.lower(), 1)
            
        # Convert template type to integer for Portainer API v2
        # Type 1 = Standalone/Podman, Type 2 = Swarm
        type_int = 1  # Default to Standalone/Podman (1)
        try:
            type_int = int(self.template_type)
        except (ValueError, TypeError):
            # In case template_type is not a numeric string, try to map it
            type_map = {
                'swarm': 2,
                'standalone': 1, 
                'podman': 1
            }
            if isinstance(self.template_type, str) and self.template_type.lower() in type_map:
                type_int = type_map.get(self.template_type.lower(), 1)
            
        # Prepare base template data according to v2 API specification
        template_data = {
            'type': type_int,
            'title': self.title,
            'description': self.description or f'Template for {self.title}',
            'note': self.note or '',
            'platform': platform_int,
            'logo': self.logo or ''
        }
        
        # Handle categories - ensure proper format for v2 API
        category_list = []
        if self.categories:
            try:
                # Try parsing as JSON first
                categories = json.loads(self.categories)
                if isinstance(categories, list):
                    category_list = [c for c in categories if isinstance(c, str)]
            except Exception:
                # Fall back to comma-separated string
                category_list = [c.strip() for c in self.categories.split(',') if c.strip()]
                
        # Add from category_ids as well
        for category in self.category_ids:
            if category.name not in category_list:
                category_list.append(category.name)
                
        template_data['categories'] = category_list or ['Custom']
        
        # Handle environment variables if specified - ensure proper format for v2 API
        if self.environment_variables:
            try:
                env_vars = json.loads(self.environment_variables)
                if isinstance(env_vars, list):
                    # Validate each environment variable has required fields
                    valid_env_vars = []
                    for env in env_vars:
                        if isinstance(env, dict) and 'name' in env:
                            valid_env_vars.append(env)
                    template_data['env'] = valid_env_vars
            except Exception as e:
                _logger.warning(f"Error parsing environment variables: {str(e)}")
                
        # Handle volumes if specified
        if self.volumes:
            try:
                volumes = json.loads(self.volumes)
                template_data['volumes'] = volumes
            except Exception as e:
                _logger.warning(f"Error parsing volumes: {str(e)}")
                
        # Handle ports if specified
        if self.ports:
            try:
                ports = json.loads(self.ports)
                template_data['ports'] = ports
            except Exception as e:
                _logger.warning(f"Error parsing ports: {str(e)}")
        
        # Add image for container templates (type 1)
        if template_data['type'] == 1 and self.image:
            template_data['image'] = self.image
            
            # Add registry if specified
            if self.registry:
                template_data['registry'] = self.registry
        
        # Handle build method for templates
        # Include fileContent for all template types if using editor method
        if self.build_method == 'editor':
            # Web editor method - always add fileContent for Portainer API v2
            # Prefer fileContent field, fall back to compose_file for backward compatibility
            compose_content = self.fileContent or self.compose_file or ''
            if compose_content:
                _logger.info(f"Using file content for template '{self.title}' (ID: {self.template_id}). Content length: {len(compose_content)} chars")
                template_data['fileContent'] = compose_content
        
        # Repository method specific settings
        if self.build_method == 'repository':
                # Git repository method
                repository_data = {
                    'url': self.git_repository_url or '',
                    'stackfile': self.git_compose_path or 'docker-compose.yml'
                }
                
                # Add reference if specified - use referenceName for v2 API
                if self.git_repository_reference:
                    repository_data['referenceName'] = self.git_repository_reference
                    
                template_data['repository'] = repository_data
                
                # Handle authentication if needed
                if self.git_authentication:
                    template_data['repositoryAuthentication'] = True
                    
                    # Use Git credentials if specified
                    if self.git_credentials_id:
                        template_data['repositoryUsername'] = self.git_credentials_id.username
                        template_data['repositoryPassword'] = self.git_credentials_id.password
                    else:
                        # Otherwise use username/token from form
                        template_data['repositoryUsername'] = self.git_username or ''
                        template_data['repositoryPassword'] = self.git_token or ''
        
        return template_data
    
    def action_create_stack(self):
        """Create a stack record using this template's name, environment, server, and file content"""
        self.ensure_one()
        
        if not self.fileContent and not self.compose_file:
            raise UserError(_("File content is required to create a stack"))
        
        # Prepare stack data
        stack_vals = {
            'name': self.title,
            'server_id': self.server_id.id,
            'environment_id': self.environment_id.id,
            'content': self.fileContent,
            'type': '2',  # Compose type (2 = Compose, 1 = Swarm)
            'custom_template_id': self.id,  # Link to the custom template
        }
        
        try:
            # Create the stack record
            stack = self.env['j_portainer.stack'].create(stack_vals)
            self.stack_id = stack.id
            return stack
            
        except Exception as e:
            _logger.error(f"Error creating stack from template {self.title}: {str(e)}")
            raise UserError(_("Error creating stack: %s") % str(e))
    
    def action_create_stack_and_open(self):
        """Create a stack record and return UI action to open it"""
        stack = self.action_create_stack()
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Created Stack'),
            'res_model': 'j_portainer.stack',
            'res_id': stack.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_view_stacks(self):
        """Open list view of stacks created from this template"""
        self.ensure_one()
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Stacks from Template: %s') % self.title,
            'res_model': 'j_portainer.stack',
            'view_mode': 'tree,form',
            'domain': [('custom_template_id', '=', self.id)],
            'context': {
                'default_custom_template_id': self.id,
                'default_server_id': self.server_id.id,
                'default_environment_id': self.environment_id.id,
            },
            'target': 'current',
        }