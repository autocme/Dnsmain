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
    _copy_default_excluded_fields = [
        'template_id', 
        'fileContent',
        'compose_file',
        'repository',
        'volumes',
        'ports',
        'environment_variables'
    ]
    
    is_custom = fields.Boolean('Custom Template', default=True, help="Used to identify custom templates")
    
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
    template_id = fields.Char('Template ID', copy=False)
    server_id = fields.Many2one('j_portainer.server', string='Server', required=True, ondelete='cascade')
    environment_id = fields.Many2one('j_portainer.environment', string='Environment', required=True,
                                domain="[('server_id', '=', server_id)]")
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
    ], string='Build Method', default='editor')
    
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
    
    @api.depends('categories')
    def _compute_category_ids(self):
        """Compute and maintain category_ids from categories text"""
        category_model = self.env['j_portainer.template.category']
        
        for template in self:
            category_list = []
            
            if template.categories:
                try:
                    # Try to parse as JSON
                    categories = json.loads(template.categories)
                    if isinstance(categories, list):
                        for category in categories:
                            if isinstance(category, str):
                                # Get or create the category
                                category_obj = category_model.search([('name', '=', category)], limit=1)
                                if not category_obj:
                                    category_obj = category_model.create({'name': category})
                                category_list.append(category_obj.id)
                            elif isinstance(category, dict) and 'name' in category:
                                # Handle object format with name key
                                category_obj = category_model.search([('name', '=', category['name'])], limit=1)
                                if not category_obj:
                                    category_obj = category_model.create({'name': category['name']})
                                category_list.append(category_obj.id)
                except Exception as e:
                    _logger.warning(f"Error parsing categories: {str(e)}")
                    # Try to parse as comma-separated string
                    try:
                        for category in template.categories.split(','):
                            category = category.strip()
                            if category:
                                category_obj = category_model.search([('name', '=', category)], limit=1)
                                if not category_obj:
                                    category_obj = category_model.create({'name': category})
                                category_list.append(category_obj.id)
                    except Exception as e2:
                        _logger.error(f"Failed to parse categories as string: {str(e2)}")
            
            template.category_ids = [(6, 0, category_list)]
    
    @api.depends('environment_variables')
    def _compute_formatted_env(self):
        """Format environment variables for display"""
        for template in self:
            result = ""
            
            if template.environment_variables:
                try:
                    env_vars = json.loads(template.environment_variables)
                    if isinstance(env_vars, list):
                        for env in env_vars:
                            if isinstance(env, dict):
                                name = env.get('name', '')
                                default_value = env.get('default', '')
                                description = env.get('description', '')
                                label = env.get('label', '')
                                
                                result += f"{name}: {default_value}\n"
                                if description:
                                    result += f"  Description: {description}\n"
                                if label:
                                    result += f"  Label: {label}\n"
                                result += "\n"
                            elif isinstance(env, str):
                                result += f"{env}\n"
                except Exception as e:
                    result = f"Error parsing environment variables: {str(e)}"
            
            template.get_formatted_env = result
    
    @api.depends('volumes')
    def _compute_formatted_volumes(self):
        """Format volumes for display"""
        for template in self:
            result = ""
            
            if template.volumes:
                try:
                    volumes = json.loads(template.volumes)
                    if isinstance(volumes, list):
                        for volume in volumes:
                            if isinstance(volume, dict):
                                container = volume.get('container', '')
                                bind = volume.get('bind', '')
                                result += f"Container: {container}\n"
                                result += f"  Bind: {bind}\n\n"
                            elif isinstance(volume, str):
                                result += f"{volume}\n"
                except Exception as e:
                    result = f"Error parsing volumes: {str(e)}"
            
            template.get_formatted_volumes = result
    
    @api.depends('fileContent')
    def _compute_compose_file(self):
        """Copy content from fileContent to compose_file field for backward compatibility"""
        for template in self:
            template.compose_file = template.fileContent
            
    def _inverse_compose_file(self):
        """Copy content from compose_file to fileContent field for backward compatibility"""
        for template in self:
            template.fileContent = template.compose_file
            
    @api.depends('ports')
    def _compute_formatted_ports(self):
        """Format ports for display"""
        for template in self:
            result = ""
            
            if template.ports:
                try:
                    ports = json.loads(template.ports)
                    if isinstance(ports, list):
                        for port in ports:
                            if isinstance(port, dict):
                                container = port.get('container', '')
                                host = port.get('host', '')
                                protocol = port.get('protocol', 'tcp')
                                result += f"Container: {container}\n"
                                result += f"  Host: {host}\n"
                                result += f"  Protocol: {protocol}\n\n"
                            elif isinstance(port, str):
                                result += f"{port}\n"
                except Exception as e:
                    result = f"Error parsing ports: {str(e)}"
            
            template.get_formatted_ports = result
    
    def action_refresh(self):
        """Refresh custom templates from Portainer"""
        for template in self:
            if template.server_id:
                template.server_id.sync_custom_templates()
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Custom Templates Refreshed'),
                        'message': _("Custom templates have been refreshed from Portainer"),
                        'sticky': False,
                    }
                }
        
        raise UserError(_("No server found to refresh custom templates"))
    
    def remove_custom_template(self):
        """Remove this custom template from Portainer"""
        self.ensure_one()
        
        # Check that the server is connected
        if self.server_id.status != 'connected':
            raise UserError(_("Cannot remove template: Server is not connected"))
            
        if not self.template_id:
            raise UserError(_("Cannot remove template: No template ID found"))
            
        # Call the API to remove the template
        api = self.env['j_portainer.api']
        result = api.template_action(self.server_id.id, self.template_id, 'delete')
        
        if result:
            # Refresh templates
            self.server_id.sync_custom_templates()
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Template Removed'),
                    'message': _("Custom template '%s' has been removed from Portainer") % self.title,
                    'sticky': False,
                    'next': {'type': 'ir.actions.act_window_close'}
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _("Failed to remove custom template from Portainer"),
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
            
        # Prepare form data
        data = {
            "Title": self.title,
            "Description": self.description or f"Auto-created from Odoo",
            "Note": self.note or "Created from Odoo j_portainer module",
            "Platform": str(platform_int),  # Must be a string for multipart form
            "Type": self.template_type,     # Already a string in our model
            "Logo": self.logo or "",
            "Variables": self.environment_variables or "[]"
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
            
            # Check response
            if response.status_code in [200, 201, 202, 204]:
                try:
                    result = response.json()
                    template_id = result.get('Id', result.get('id'))
                    
                    if template_id:
                        # Update template ID in Odoo
                        self.write({'template_id': template_id})
                        
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
                        # For updates, include template ID in the URL
                        url = f"{server_url}/api/custom_templates/{template_id}"
                    
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
                            'Type': str(type_value),  # 1 for container, 2 for stack, 3 for app template
                            'Logo': self.logo or '',
                        }
                        
                        # Add environment ID - this is critical for the API request
                        if portainer_env_id:
                            data['environmentId'] = str(portainer_env_id)
                        
                        # Add variables if available
                        if self.environment_variables:
                            data['Variables'] = self.environment_variables
                            
                        # Prepare files for upload
                        files = {
                            'File': ('template.yml', file_content.encode('utf-8'))
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
                        
                        # Send the POST request - skip SSL verification for self-signed certs
                        res = requests.post(url, headers=headers, data=data, files=files, verify=False)
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
                            json_data['Variables'] = []
                            try:
                                import json
                                if isinstance(self.environment_variables, str):
                                    env_vars = json.loads(self.environment_variables)
                                    json_data['Variables'] = env_vars
                            except Exception as e:
                                _logger.warning(f"Failed to parse variables: {e}")
                        
                        # Add file content directly in the JSON payload
                        if file_content:
                            json_data['FileContent'] = file_content
                        
                        # Add specific headers for JSON
                        json_headers = headers.copy()
                        json_headers['Content-Type'] = 'application/json'
                        
                        # Log the complete request for debugging
                        _logger.info(f"PUT Request URL: {url}")
                        _logger.info(f"PUT Request Headers: {json_headers}")
                        _logger.info(f"PUT Request JSON: {json.dumps(json_data)}")
                        
                        # Send the PUT request - skip SSL verification for self-signed certs
                        res = requests.put(url, headers=json_headers, json=json_data, verify=False)
                    
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
                            'Type': str(type_value),  # 1 for container, 2 for stack, 3 for app template
                            'Logo': self.logo or '',
                        }
                        
                        # Add environment ID - this is critical for the API request
                        if portainer_env_id:
                            post_data['environmentId'] = str(portainer_env_id)
                            
                        # Add variables if available
                        if self.environment_variables:
                            post_data['Variables'] = self.environment_variables
                            
                        # Prepare files for upload
                        post_files = {
                            'File': ('template.yml', file_content.encode('utf-8'))
                        }
                        
                        _logger.info(f"Sending fallback multipart form POST request to {create_url}")
                        create_res = requests.post(url=create_url, headers=headers, data=post_data, files=post_files, verify=False)
                        
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
                response = api.update_template(server_id, template_id, template_data)
                
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
                _logger.info(f"Updating template with data: {json.dumps(update_data, indent=2)}")
                
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
        
        # Skip Portainer creation if skip_portainer_create flag is set or if manual template ID was provided
        if vals.get('skip_portainer_create') or vals.get('manual_template_id'):
            return record
            
        # Auto-create in Portainer using the direct file upload API
        try:
            # Call the action_create_in_portainer method without raising exceptions
            # This ensures the record is still created in Odoo even if Portainer creation fails
            import requests
            import json
            
            # Get server details
            server = record.server_id
            portainer_env_id = record.environment_id.environment_id
            
            # Prepare the endpoint URL
            url = f"{server.url.rstrip('/')}/api/custom_templates/create/file?environment={portainer_env_id}"
            
            # Prepare headers with API key
            headers = {
                "X-API-Key": server._get_api_key_header()
            }
            
            # Convert platform and type to integer format as expected by Portainer
            platform_int = 1  # Default to Linux (1)
            if record.platform:
                platform_map = {
                    'linux': 1,
                    'windows': 2
                }
                platform_int = platform_map.get(record.platform.lower(), 1)
                
            # Prepare form data
            data = {
                "Title": record.title,
                "Description": record.description or f"Auto-created from Odoo",
                "Note": record.note or "Created from Odoo j_portainer module",
                "Platform": str(platform_int),  # Must be a string for multipart form
                "Type": record.template_type,   # Already a string in our model
                "Logo": record.logo or "",
                "Variables": record.environment_variables or "[]"
            }
            
            # Add categories if available
            if record.categories:
                try:
                    # Try to format categories as JSON string
                    categories = record.categories.split(",") if isinstance(record.categories, str) else []
                    data["Categories"] = json.dumps(categories)
                except Exception as e:
                    _logger.warning(f"Error formatting categories: {str(e)}")
            
            # Prepare the file content
            file_content = record.fileContent or record.compose_file or ""
            if file_content:
                # Prepare the file for upload
                files = {
                    "File": ("template.yml", file_content.encode('utf-8'), "text/x-yaml")
                }
                
                try:
                    _logger.info(f"Auto-creating template in Portainer at URL: {url}")
                    _logger.info(f"Template data: {data}")
                    
                    # Make the request with SSL verification as configured in server
                    response = requests.post(
                        url, 
                        headers=headers,
                        data=data,
                        files=files,
                        verify=server.verify_ssl
                    )
                    
                    # Check response
                    if response.status_code in [200, 201, 202, 204]:
                        try:
                            result = response.json()
                            template_id = result.get('Id', result.get('id'))
                            
                            if template_id:
                                # Update template ID in Odoo
                                record.write({'template_id': template_id})
                                _logger.info(f"Template created successfully in Portainer with ID: {template_id}")
                        except Exception as e:
                            _logger.warning(f"Couldn't parse JSON response: {str(e)}")
                    else:
                        # Log error but don't raise exception - we still want to create the record in Odoo
                        error_message = response.text
                        try:
                            error_data = response.json()
                            if isinstance(error_data, dict) and 'message' in error_data:
                                error_message = error_data['message']
                        except Exception:
                            pass
                        
                        _logger.warning(f"Error creating template in Portainer: {error_message} (status: {response.status_code})")
                        
                except requests.exceptions.RequestException as e:
                    _logger.warning(f"Error connecting to Portainer: {str(e)}")
            else:
                _logger.warning("Skipping auto-create in Portainer: No file content available")
                
        except Exception as e:
            _logger.warning(f"Error during auto-create in Portainer (record still created in Odoo): {str(e)}")
            
        return record
        
    def write(self, vals):
        """Override write to sync with Portainer"""
        result = super(PortainerCustomTemplate, self).write(vals)
        
        # Skip Portainer update if we're just updating from a sync operation
        if not self.env.context.get('skip_portainer_update'):
            for template in self:
                if template.template_id and template.server_id.status == 'connected':
                    try:
                        # Skip if we're just setting skip_portainer_create flag
                        if len(vals) == 1 and 'skip_portainer_create' in vals:
                            continue
                        
                        # Sync the template to Portainer
                        response = template._sync_to_portainer(method='put')
                        
                        if not response:
                            _logger.warning(f"Could not update template {template.id} in Portainer")
                    except Exception as e:
                        _logger.error(f"Error updating template {template.id} in Portainer: {str(e)}")
        
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
            
        # Prepare base template data according to v2 API specification
        template_data = {
            'type': int(self.template_type),
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