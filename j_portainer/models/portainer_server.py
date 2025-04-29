#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import requests
import logging
import json
from datetime import datetime
import urllib3

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_logger = logging.getLogger(__name__)

class PortainerServer(models.Model):
    _name = 'j_portainer.server'
    _description = 'Portainer Server'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    
    name = fields.Char('Name', required=True, tracking=True)
    url = fields.Char('URL', required=True, tracking=True,
                     help="URL to Portainer server (e.g., https://portainer.example.com:9443)")
    api_key = fields.Char('API Key', required=True, tracking=True, 
                       help="Portainer API key for authentication")
    verify_ssl = fields.Boolean('Verify SSL', default=True, tracking=True,
                               help="Verify SSL certificates when connecting")
    status = fields.Selection([
        ('unknown', 'Unknown'),
        ('connecting', 'Connecting'),
        ('connected', 'Connected'),
        ('error', 'Error')
    ], string='Status', default='unknown', readonly=True, tracking=True)
    last_sync = fields.Datetime('Last Synchronization', readonly=True, tracking=True)
    error_message = fields.Text('Error Message', readonly=True)
    portainer_version = fields.Char('Portainer Version', readonly=True)
    portainer_info = fields.Text('Server Info', readonly=True)
    environment_count = fields.Integer('Environments', readonly=True)
    
    # Related Resources
    container_ids = fields.One2many('j_portainer.container', 'server_id', string='Containers')
    image_ids = fields.One2many('j_portainer.image', 'server_id', string='Images')
    volume_ids = fields.One2many('j_portainer.volume', 'server_id', string='Volumes')
    network_ids = fields.One2many('j_portainer.network', 'server_id', string='Networks')
    template_ids = fields.One2many('j_portainer.template', 'server_id', string='Templates')
    stack_ids = fields.One2many('j_portainer.stack', 'server_id', string='Stacks')
    environment_ids = fields.One2many('j_portainer.environment', 'server_id', string='Environments')
    
    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'Server name must be unique!')
    ]
    
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            record.test_connection()
        return records
    
    def write(self, vals):
        # If connection parameters changed, test connection
        if 'url' in vals or 'api_key' in vals or 'verify_ssl' in vals:
            result = super().write(vals)
            self.test_connection()
            return result
        return super().write(vals)
    
    def test_connection(self):
        """Test connection to the Portainer server"""
        self.ensure_one()
        
        try:
            self.status = 'connecting'
            self._cr.commit()  # Commit the transaction to update the UI
            
            # Make API request to get system status
            response = self._make_api_request('/api/system/status', 'GET')
            
            if response.status_code == 200:
                status_data = response.json()
                version = status_data.get('Version', 'Unknown')
                
                # Get additional system info
                info_response = self._make_api_request('/api/system/info', 'GET')
                info_data = info_response.json() if info_response.status_code == 200 else {}
                
                # Get endpoints (environments) count
                endpoints_response = self._make_api_request('/api/endpoints', 'GET')
                endpoints_data = endpoints_response.json() if endpoints_response.status_code == 200 else []
                
                # Update server info
                self.write({
                    'status': 'connected',
                    'last_sync': fields.Datetime.now(),
                    'error_message': False,
                    'portainer_version': version,
                    'portainer_info': json.dumps(info_data, indent=2) if info_data else '',
                    'environment_count': len(endpoints_data),
                })
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Connection Successful'),
                        'message': _('Successfully connected to Portainer server (version %s)') % version,
                        'sticky': False,
                        'type': 'success',
                    }
                }
            else:
                error_msg = _("API Error: %s") % response.text
                self.write({
                    'status': 'error',
                    'error_message': error_msg
                })
                raise UserError(error_msg)
                
        except Exception as e:
            _logger.error(f"Connection error: {str(e)}")
            self.write({
                'status': 'error',
                'error_message': str(e)
            })
            raise UserError(_("Connection error: %s") % str(e))
    
    def _make_api_request(self, endpoint, method='GET', data=None, params=None):
        """Make a request to the Portainer API
        
        Args:
            endpoint (str): API endpoint (e.g., '/api/endpoints')
            method (str): HTTP method (GET, POST, PUT, DELETE)
            data (dict, optional): Request payload for POST/PUT
            params (dict, optional): URL parameters
            
        Returns:
            requests.Response: API response
        """
        url = self.url.rstrip('/') + endpoint
        headers = {
            'X-API-Key': self.api_key,
            'Content-Type': 'application/json'
        }
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params, 
                                      verify=self.verify_ssl, timeout=10)
            elif method == 'POST':
                response = requests.post(url, headers=headers, json=data,
                                       verify=self.verify_ssl, timeout=10)
            elif method == 'PUT':
                response = requests.put(url, headers=headers, json=data,
                                      verify=self.verify_ssl, timeout=10)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers,
                                        verify=self.verify_ssl, timeout=10)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
                
            return response
            
        except requests.exceptions.ConnectionError as e:
            _logger.error(f"Connection error: {str(e)}")
            raise UserError(_("Connection error: Could not connect to Portainer server at %s. Please check the URL and network connectivity.") % self.url)
        except requests.exceptions.Timeout:
            _logger.error("Connection timeout")
            raise UserError(_("Connection timeout: The request to Portainer server timed out. Please try again later."))
        except requests.exceptions.RequestException as e:
            _logger.error(f"Request error: {str(e)}")
            raise UserError(_("Request error: %s") % str(e))
            
    def sync_environments(self):
        """Sync environments from Portainer"""
        self.ensure_one()
        
        try:
            # Clear existing environments
            self.environment_ids.unlink()
            
            # Get all endpoints
            response = self._make_api_request('/api/endpoints', 'GET')
            if response.status_code != 200:
                raise UserError(_("Failed to get environments: %s") % response.text)
                
            environments = response.json()
            for env in environments:
                env_id = env.get('Id')
                env_name = env.get('Name', 'Unknown')
                
                # Get endpoint details
                details_response = self._make_api_request(f'/api/endpoints/{env_id}', 'GET')
                details = details_response.json() if details_response.status_code == 200 else {}
                
                self.env['j_portainer.environment'].create({
                    'server_id': self.id,
                    'environment_id': env_id,
                    'name': env_name,
                    'url': env.get('URL', ''),
                    'status': 'up' if env.get('Status') == 1 else 'down',
                    'type': env.get('Type', 0),
                    'public_url': env.get('PublicURL', ''),
                    'group_id': env.get('GroupId'),
                    'group_name': env.get('GroupName', ''),
                    'tags': ','.join(env.get('Tags', [])),
                    'details': json.dumps(details, indent=2) if details else '',
                })
            
            self.write({
                'last_sync': fields.Datetime.now(),
                'environment_count': len(environments)
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Environments Synchronized'),
                    'message': _('%d environments found') % len(environments),
                    'sticky': False,
                    'type': 'success',
                }
            }
            
        except Exception as e:
            _logger.error(f"Error syncing environments: {str(e)}")
            raise UserError(_("Error syncing environments: %s") % str(e))
    
    def sync_containers(self, environment_id=None):
        """Sync containers from Portainer
        
        Args:
            environment_id (int, optional): Environment ID to sync containers for.
                If not provided, syncs containers for all environments.
        """
        self.ensure_one()
        
        try:
            # Clear existing containers for the given environment or all environments
            if environment_id:
                self.env['j_portainer.container'].search([
                    ('server_id', '=', self.id),
                    ('environment_id', '=', environment_id)
                ]).unlink()
                environments = self.environment_ids.filtered(lambda e: e.environment_id == environment_id)
            else:
                self.container_ids.unlink()
                environments = self.environment_ids
            
            container_count = 0
            
            # Sync containers for each environment
            for env in environments:
                endpoint_id = env.environment_id
                
                # Get all containers for this endpoint
                response = self._make_api_request(f'/api/endpoints/{endpoint_id}/docker/containers/json', 'GET', 
                                              params={'all': True})
                
                if response.status_code != 200:
                    _logger.warning(f"Failed to get containers for environment {env.name}: {response.text}")
                    continue
                    
                containers = response.json()
                
                for container in containers:
                    container_id = container.get('Id')
                    
                    # Get container details
                    details_response = self._make_api_request(
                        f'/api/endpoints/{endpoint_id}/docker/containers/{container_id}/json', 'GET')
                    
                    details = details_response.json() if details_response.status_code == 200 else {}
                    
                    # Get container state 
                    state = details.get('State', {})
                    status = state.get('Status', 'unknown')
                    
                    # Create container record
                    self.env['j_portainer.container'].create({
                        'server_id': self.id,
                        'environment_id': endpoint_id,
                        'environment_name': env.name,
                        'container_id': container_id,
                        'name': container.get('Names', ['Unknown'])[0].lstrip('/'),
                        'image': container.get('Image', ''),
                        'image_id': container.get('ImageID', ''),
                        'created': datetime.fromtimestamp(container.get('Created', 0)),
                        'status': status,
                        'state': 'running' if state.get('Running', False) else 'stopped',
                        'ports': json.dumps(container.get('Ports', [])),
                        'labels': json.dumps(container.get('Labels', {})),
                        'details': json.dumps(details, indent=2) if details else '',
                    })
                    container_count += 1
            
            self.write({'last_sync': fields.Datetime.now()})
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Containers Synchronized'),
                    'message': _('%d containers found') % container_count,
                    'sticky': False,
                    'type': 'success',
                }
            }
            
        except Exception as e:
            _logger.error(f"Error syncing containers: {str(e)}")
            raise UserError(_("Error syncing containers: %s") % str(e))
            
    def sync_images(self, environment_id=None):
        """Sync images from Portainer
        
        Args:
            environment_id (int, optional): Environment ID to sync images for.
                If not provided, syncs images for all environments.
        """
        self.ensure_one()
        
        try:
            # Clear existing images for the given environment or all environments
            if environment_id:
                self.env['j_portainer.image'].search([
                    ('server_id', '=', self.id),
                    ('environment_id', '=', environment_id)
                ]).unlink()
                environments = self.environment_ids.filtered(lambda e: e.environment_id == environment_id)
            else:
                self.image_ids.unlink()
                environments = self.environment_ids
            
            image_count = 0
            
            # Sync images for each environment
            for env in environments:
                endpoint_id = env.environment_id
                
                # Get all images for this endpoint
                response = self._make_api_request(f'/api/endpoints/{endpoint_id}/docker/images/json', 'GET')
                
                if response.status_code != 200:
                    _logger.warning(f"Failed to get images for environment {env.name}: {response.text}")
                    continue
                    
                images = response.json()
                
                for image in images:
                    image_id = image.get('Id')
                    
                    # Get tags (repos)
                    repos = image.get('RepoTags', [])
                    
                    # Get image details
                    details_response = self._make_api_request(
                        f'/api/endpoints/{endpoint_id}/docker/images/{image_id}/json', 'GET')
                    
                    details = details_response.json() if details_response.status_code == 200 else {}
                    
                    # Create images - one for each repo tag
                    if repos and repos[0] != '<none>:<none>':
                        for repo in repos:
                            if ':' in repo:
                                repository, tag = repo.split(':', 1)
                            else:
                                repository, tag = repo, 'latest'
                                
                            self.env['j_portainer.image'].create({
                                'server_id': self.id,
                                'environment_id': endpoint_id,
                                'environment_name': env.name,
                                'image_id': image_id,
                                'repository': repository,
                                'tag': tag,
                                'created': datetime.fromtimestamp(image.get('Created', 0)),
                                'size': image.get('Size', 0),
                                'shared_size': image.get('SharedSize', 0),
                                'virtual_size': image.get('VirtualSize', 0),
                                'labels': json.dumps(image.get('Labels', {})),
                                'details': json.dumps(details, indent=2) if details else '',
                            })
                            image_count += 1
                    else:
                        # Untagged image
                        self.env['j_portainer.image'].create({
                            'server_id': self.id,
                            'environment_id': endpoint_id,
                            'environment_name': env.name,
                            'image_id': image_id,
                            'repository': '<none>',
                            'tag': '<none>',
                            'created': datetime.fromtimestamp(image.get('Created', 0)),
                            'size': image.get('Size', 0),
                            'shared_size': image.get('SharedSize', 0),
                            'virtual_size': image.get('VirtualSize', 0),
                            'labels': json.dumps(image.get('Labels', {})),
                            'details': json.dumps(details, indent=2) if details else '',
                        })
                        image_count += 1
            
            self.write({'last_sync': fields.Datetime.now()})
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Images Synchronized'),
                    'message': _('%d images found') % image_count,
                    'sticky': False,
                    'type': 'success',
                }
            }
            
        except Exception as e:
            _logger.error(f"Error syncing images: {str(e)}")
            raise UserError(_("Error syncing images: %s") % str(e))
    
    def sync_volumes(self, environment_id=None):
        """Sync volumes from Portainer
        
        Args:
            environment_id (int, optional): Environment ID to sync volumes for.
                If not provided, syncs volumes for all environments.
        """
        self.ensure_one()
        
        try:
            # Clear existing volumes for the given environment or all environments
            if environment_id:
                self.env['j_portainer.volume'].search([
                    ('server_id', '=', self.id),
                    ('environment_id', '=', environment_id)
                ]).unlink()
                environments = self.environment_ids.filtered(lambda e: e.environment_id == environment_id)
            else:
                self.volume_ids.unlink()
                environments = self.environment_ids
            
            volume_count = 0
            
            # Sync volumes for each environment
            for env in environments:
                endpoint_id = env.environment_id
                
                # Get all volumes for this endpoint
                response = self._make_api_request(f'/api/endpoints/{endpoint_id}/docker/volumes', 'GET')
                
                if response.status_code != 200:
                    _logger.warning(f"Failed to get volumes for environment {env.name}: {response.text}")
                    continue
                    
                volumes_data = response.json()
                volumes = volumes_data.get('Volumes', [])
                
                for volume in volumes:
                    volume_name = volume.get('Name')
                    
                    # Get detailed info for this volume
                    details_response = self._make_api_request(
                        f'/api/endpoints/{endpoint_id}/docker/volumes/{volume_name}', 'GET')
                    
                    details = details_response.json() if details_response.status_code == 200 else {}
                    
                    self.env['j_portainer.volume'].create({
                        'server_id': self.id,
                        'environment_id': endpoint_id,
                        'environment_name': env.name,
                        'name': volume_name,
                        'driver': volume.get('Driver', ''),
                        'mountpoint': volume.get('Mountpoint', ''),
                        'created': datetime.now(),  # Docker volumes don't have created date
                        'scope': volume.get('Scope', 'local'),
                        'labels': json.dumps(volume.get('Labels', {})),
                        'details': json.dumps(details, indent=2) if details else '',
                    })
                    volume_count += 1
            
            self.write({'last_sync': fields.Datetime.now()})
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Volumes Synchronized'),
                    'message': _('%d volumes found') % volume_count,
                    'sticky': False,
                    'type': 'success',
                }
            }
            
        except Exception as e:
            _logger.error(f"Error syncing volumes: {str(e)}")
            raise UserError(_("Error syncing volumes: %s") % str(e))
            
    def sync_networks(self, environment_id=None):
        """Sync networks from Portainer
        
        Args:
            environment_id (int, optional): Environment ID to sync networks for.
                If not provided, syncs networks for all environments.
        """
        self.ensure_one()
        
        try:
            # Clear existing networks for the given environment or all environments
            if environment_id:
                self.env['j_portainer.network'].search([
                    ('server_id', '=', self.id),
                    ('environment_id', '=', environment_id)
                ]).unlink()
                environments = self.environment_ids.filtered(lambda e: e.environment_id == environment_id)
            else:
                self.network_ids.unlink()
                environments = self.environment_ids
            
            network_count = 0
            
            # Sync networks for each environment
            for env in environments:
                endpoint_id = env.environment_id
                
                # Get all networks for this endpoint
                response = self._make_api_request(f'/api/endpoints/{endpoint_id}/docker/networks', 'GET')
                
                if response.status_code != 200:
                    _logger.warning(f"Failed to get networks for environment {env.name}: {response.text}")
                    continue
                    
                networks = response.json()
                
                for network in networks:
                    network_id = network.get('Id')
                    
                    # Get detailed info for this network
                    details_response = self._make_api_request(
                        f'/api/endpoints/{endpoint_id}/docker/networks/{network_id}', 'GET')
                    
                    details = details_response.json() if details_response.status_code == 200 else {}
                    
                    self.env['j_portainer.network'].create({
                        'server_id': self.id,
                        'environment_id': endpoint_id,
                        'environment_name': env.name,
                        'network_id': network_id,
                        'name': network.get('Name', ''),
                        'driver': network.get('Driver', ''),
                        'scope': network.get('Scope', 'local'),
                        'ipam': json.dumps(network.get('IPAM', {})),
                        'labels': json.dumps(network.get('Labels', {})),
                        'containers': json.dumps(network.get('Containers', {})),
                        'details': json.dumps(details, indent=2) if details else '',
                    })
                    network_count += 1
            
            self.write({'last_sync': fields.Datetime.now()})
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Networks Synchronized'),
                    'message': _('%d networks found') % network_count,
                    'sticky': False,
                    'type': 'success',
                }
            }
            
        except Exception as e:
            _logger.error(f"Error syncing networks: {str(e)}")
            raise UserError(_("Error syncing networks: %s") % str(e))
    
    def sync_templates(self):
        """Sync application templates from Portainer"""
        self.ensure_one()
        
        try:
            # Clear existing templates
            self.template_ids.unlink()
            
            # Get templates
            response = self._make_api_request('/api/templates', 'GET')
            
            if response.status_code != 200:
                raise UserError(_("Failed to get templates: %s") % response.text)
                
            templates = response.json()
            template_count = 0
            
            for template in templates:
                self.env['j_portainer.template'].create({
                    'server_id': self.id,
                    'title': template.get('title', ''),
                    'description': template.get('description', ''),
                    'template_type': template.get('type', 1),  # 1 = container, 2 = stack
                    'platform': template.get('platform', 'linux'),
                    'template_id': template.get('id'),
                    'logo': template.get('logo', ''),
                    'registry': template.get('registry', ''),
                    'image': template.get('image', ''),
                    'repository': template.get('repository', {}),
                    'categories': ','.join(template.get('categories', [])),
                    'env': json.dumps(template.get('env', [])),
                    'volumes': json.dumps(template.get('volumes', [])),
                    'ports': json.dumps(template.get('ports', [])),
                    'note': template.get('note', ''),
                    'is_custom': False,
                })
                template_count += 1
            
            # Get custom templates
            custom_response = self._make_api_request('/api/custom_templates', 'GET')
            
            if custom_response.status_code == 200:
                custom_templates = custom_response.json()
                
                for template in custom_templates:
                    self.env['j_portainer.template'].create({
                        'server_id': self.id,
                        'title': template.get('title', ''),
                        'description': template.get('description', ''),
                        'template_type': template.get('type', 1),
                        'platform': template.get('platform', 'linux'),
                        'template_id': template.get('id'),
                        'logo': template.get('logo', ''),
                        'image': template.get('image', ''),
                        'repository': template.get('repository', {}),
                        'categories': ','.join(template.get('categories', [])),
                        'env': json.dumps(template.get('env', [])),
                        'volumes': json.dumps(template.get('volumes', [])),
                        'ports': json.dumps(template.get('ports', [])),
                        'note': template.get('note', ''),
                        'is_custom': True,
                    })
                    template_count += 1
            
            self.write({'last_sync': fields.Datetime.now()})
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Templates Synchronized'),
                    'message': _('%d templates found') % template_count,
                    'sticky': False,
                    'type': 'success',
                }
            }
            
        except Exception as e:
            _logger.error(f"Error syncing templates: {str(e)}")
            raise UserError(_("Error syncing templates: %s") % str(e))
            
    def sync_stacks(self, environment_id=None):
        """Sync stacks from Portainer
        
        Args:
            environment_id (int, optional): Environment ID to sync stacks for.
                If not provided, syncs stacks for all environments.
        """
        self.ensure_one()
        
        try:
            # Clear existing stacks for the given environment or all environments
            if environment_id:
                self.env['j_portainer.stack'].search([
                    ('server_id', '=', self.id),
                    ('environment_id', '=', environment_id)
                ]).unlink()
                environments = self.environment_ids.filtered(lambda e: e.environment_id == environment_id)
            else:
                self.stack_ids.unlink()
                environments = self.environment_ids
            
            stack_count = 0
            
            # Sync stacks for each environment
            for env in environments:
                endpoint_id = env.environment_id
                
                # Get all stacks
                response = self._make_api_request('/api/stacks', 'GET')
                
                if response.status_code != 200:
                    _logger.warning(f"Failed to get stacks: {response.text}")
                    continue
                    
                stacks = response.json()
                
                # Filter stacks for this environment
                env_stacks = [s for s in stacks if s.get('EndpointId') == endpoint_id]
                
                for stack in env_stacks:
                    stack_id = stack.get('Id')
                    
                    # Get stack file content if available
                    file_content = ''
                    file_response = self._make_api_request(f'/api/stacks/{stack_id}/file', 'GET')
                    if file_response.status_code == 200:
                        file_data = file_response.json()
                        file_content = file_data.get('StackFileContent', '')
                    
                    self.env['j_portainer.stack'].create({
                        'server_id': self.id,
                        'environment_id': endpoint_id,
                        'environment_name': env.name,
                        'stack_id': stack_id,
                        'name': stack.get('Name', ''),
                        'type': stack.get('Type', 1),
                        'status': stack.get('Status', 0),
                        'creation_date': datetime.fromisoformat(stack.get('CreationDate').replace('Z', '+00:00')) 
                                      if stack.get('CreationDate') else datetime.now(),
                        'update_date': datetime.fromisoformat(stack.get('UpdateDate').replace('Z', '+00:00')) 
                                    if stack.get('UpdateDate') else None,
                        'file_content': file_content,
                        'details': json.dumps(stack, indent=2),
                    })
                    stack_count += 1
            
            self.write({'last_sync': fields.Datetime.now()})
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Stacks Synchronized'),
                    'message': _('%d stacks found') % stack_count,
                    'sticky': False,
                    'type': 'success',
                }
            }
            
        except Exception as e:
            _logger.error(f"Error syncing stacks: {str(e)}")
            raise UserError(_("Error syncing stacks: %s") % str(e))
    
    def sync_all(self):
        """Sync all resources from Portainer"""
        self.ensure_one()
        
        try:
            # Sync environments first
            self.sync_environments()
            
            # Sync all other resources
            self.sync_containers()
            self.sync_images()
            self.sync_volumes()
            self.sync_networks()
            self.sync_templates()
            self.sync_stacks()
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Synchronization Complete'),
                    'message': _('All Portainer resources have been synchronized.'),
                    'sticky': False,
                    'type': 'success',
                }
            }
            
        except Exception as e:
            _logger.error(f"Error during full sync: {str(e)}")
            raise UserError(_("Error during full sync: %s") % str(e))