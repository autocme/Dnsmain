#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import requests
import logging
import json
from datetime import datetime
import urllib3
from typing import Optional, Union, Any

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_logger = logging.getLogger(__name__)

class PortainerServer(models.Model):
    _name = 'j_portainer.server'
    _description = 'Portainer Server'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    
    def _parse_date_value(self, date_value: Any) -> Optional[datetime]:
        """Parse date value from API response
        
        Handles different date formats from the Portainer API including:
        - ISO format strings (2022-01-01T00:00:00Z)
        - Integer timestamps
        - None values
        
        Args:
            date_value: Date value from API response
            
        Returns:
            datetime object or None if value cannot be parsed
        """
        if not date_value:
            return None
            
        try:
            if isinstance(date_value, str):
                # Handle ISO format string
                return datetime.fromisoformat(date_value.replace('Z', '+00:00'))
            elif isinstance(date_value, int):
                # Handle timestamp
                return datetime.fromtimestamp(date_value)
            else:
                _logger.warning(f"Unsupported date format: {date_value} ({type(date_value)})")
                return None
        except Exception as e:
            _logger.warning(f"Error parsing date value {date_value}: {str(e)}")
            return None
    
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
    custom_template_ids = fields.One2many('j_portainer.customtemplate', 'server_id', string='Custom Templates')
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
    
    def _get_api_key_header(self):
        """Get the API key header for authentication
        
        Returns:
            str: API key header value
        """
        if not self.api_key:
            return None
            
        # Format header value for X-API-Key authentication
        return f"{self.api_key}"
        
    def _make_api_request(self, endpoint, method='GET', data=None, params=None, headers=None):
        """Make a request to the Portainer API
        
        Args:
            endpoint (str): API endpoint (e.g., '/api/endpoints')
            method (str): HTTP method (GET, POST, PUT, DELETE)
            data (dict, optional): Request payload for POST/PUT
            params (dict, optional): URL parameters
            headers (dict, optional): Additional headers to include with the request
            
        Returns:
            requests.Response: API response
        """
        url = self.url.rstrip('/') + endpoint
        
        # Default headers
        request_headers = {
            'X-API-Key': self._get_api_key_header(),
            'Content-Type': 'application/json'
        }
        
        # Update with any additional headers
        if headers:
            request_headers.update(headers)
            
        try:
            _logger.debug(f"Making {method} request to {url}")
            
            if method == 'GET':
                response = requests.get(url, headers=request_headers, params=params, 
                                      verify=self.verify_ssl, timeout=15)
            elif method == 'POST':
                _logger.debug(f"POST request data: {json.dumps(data, indent=2) if data else None}")
                response = requests.post(url, headers=request_headers, json=data,
                                       verify=self.verify_ssl, timeout=15)
            elif method == 'PUT':
                response = requests.put(url, headers=request_headers, json=data,
                                      verify=self.verify_ssl, timeout=15)
            elif method == 'DELETE':
                response = requests.delete(url, headers=request_headers, params=params,
                                        verify=self.verify_ssl, timeout=15)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
                
            _logger.debug(f"API response status: {response.status_code}")
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
                    'tags': ','.join(env.get('Tags', [])) if isinstance(env.get('Tags', []), list) else '',
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
            # Keep track of synced container IDs to mark missing ones as inactive
            synced_container_ids = []
            
            # Get environments to sync
            if environment_id:
                environments = self.environment_ids.filtered(lambda e: e.environment_id == environment_id)
            else:
                environments = self.environment_ids
            
            container_count = 0
            updated_count = 0
            created_count = 0
            
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
                    container_name = container.get('Names', ['Unknown'])[0].lstrip('/')
                    
                    # Check if container already exists in Odoo
                    existing_container = self.env['j_portainer.container'].search([
                        ('server_id', '=', self.id),
                        ('environment_id', '=', endpoint_id),
                        ('container_id', '=', container_id)
                    ], limit=1)
                    
                    # Get container details
                    details_response = self._make_api_request(
                        f'/api/endpoints/{endpoint_id}/docker/containers/{container_id}/json', 'GET')
                    
                    details = details_response.json() if details_response.status_code == 200 else {}
                    
                    # Get container state 
                    state = details.get('State', {})
                    status = state.get('Status', 'unknown')
                    
                    # Extract volume information from container details
                    volumes_data = []
                    mounts = details.get('Mounts', [])
                    if mounts:
                        volumes_data = mounts
                    
                    # Prepare data for create/update
                    container_data = {
                        'server_id': self.id,
                        'environment_id': endpoint_id,
                        'environment_name': env.name,
                        'container_id': container_id,
                        'name': container_name,
                        'image': container.get('Image', ''),
                        'image_id': container.get('ImageID', ''),
                        'created': datetime.fromtimestamp(container.get('Created', 0)),
                        'status': status,
                        'state': 'running' if state.get('Running', False) else 'stopped',
                        'ports': json.dumps(container.get('Ports', [])),
                        'labels': json.dumps(container.get('Labels', {})),
                        'details': json.dumps(details, indent=2) if details else '',
                        'volumes': json.dumps(volumes_data),
                    }
                    
                    if existing_container:
                        # Update existing container record
                        existing_container.write(container_data)
                        updated_count += 1
                    else:
                        # Create new container record
                        self.env['j_portainer.container'].create(container_data)
                        created_count += 1
                    
                    synced_container_ids.append(container_id)
                    container_count += 1
                    
            # Log the statistics
            _logger.info(f"Container sync complete: {container_count} total containers, {created_count} created, {updated_count} updated")
            
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
            # Keep track of synced image IDs 
            synced_image_ids = []
            
            # Get environments to sync
            if environment_id:
                environments = self.environment_ids.filtered(lambda e: e.environment_id == environment_id)
            else:
                environments = self.environment_ids
            
            image_count = 0
            updated_count = 0
            created_count = 0
            
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
                    
                    # Prepare base image data
                    base_image_data = {
                        'server_id': self.id,
                        'environment_id': endpoint_id,
                        'environment_name': env.name,
                        'image_id': image_id,
                        'created': datetime.fromtimestamp(image.get('Created', 0)),
                        'size': image.get('Size', 0),
                        'shared_size': image.get('SharedSize', 0),
                        'virtual_size': image.get('VirtualSize', 0),
                        'labels': json.dumps(image.get('Labels', {})),
                        'details': json.dumps(details, indent=2) if details else '',
                    }
                    
                    # Process images - one for each repo tag
                    if repos and repos[0] != '<none>:<none>':
                        for repo in repos:
                            if ':' in repo:
                                repository, tag = repo.split(':', 1)
                            else:
                                repository, tag = repo, 'latest'
                                
                            # Check if this image already exists in Odoo
                            existing_image = self.env['j_portainer.image'].search([
                                ('server_id', '=', self.id),
                                ('environment_id', '=', endpoint_id),
                                ('image_id', '=', image_id),
                                ('repository', '=', repository),
                                ('tag', '=', tag)
                            ], limit=1)
                            
                            # Prepare specific image data with repository and tag
                            image_data = dict(base_image_data)
                            image_data.update({
                                'repository': repository,
                                'tag': tag
                            })
                            
                            if existing_image:
                                # Update existing image record
                                existing_image.write(image_data)
                                updated_count += 1
                            else:
                                # Create new image record
                                self.env['j_portainer.image'].create(image_data)
                                created_count += 1
                                
                            image_count += 1
                            synced_image_ids.append((image_id, repository, tag))
                    else:
                        # Untagged image
                        # Check if this untagged image already exists in Odoo
                        existing_image = self.env['j_portainer.image'].search([
                            ('server_id', '=', self.id),
                            ('environment_id', '=', endpoint_id),
                            ('image_id', '=', image_id),
                            ('repository', '=', '<none>'),
                            ('tag', '=', '<none>')
                        ], limit=1)
                        
                        # Prepare untagged image data
                        image_data = dict(base_image_data)
                        image_data.update({
                            'repository': '<none>',
                            'tag': '<none>'
                        })
                        
                        if existing_image:
                            # Update existing image record
                            existing_image.write(image_data)
                            updated_count += 1
                        else:
                            # Create new image record
                            self.env['j_portainer.image'].create(image_data)
                            created_count += 1
                            
                        image_count += 1
                        synced_image_ids.append((image_id, '<none>', '<none>'))
            
            # Log the statistics
            _logger.info(f"Image sync complete: {image_count} total images, {created_count} created, {updated_count} updated")
            
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
            # Keep track of synced volumes
            synced_volume_names = []
            
            # Get environments to sync
            if environment_id:
                environments = self.environment_ids.filtered(lambda e: e.environment_id == environment_id)
            else:
                environments = self.environment_ids
            
            volume_count = 0
            updated_count = 0
            created_count = 0
            
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
                    
                    # Check if this volume already exists in Odoo
                    existing_volume = self.env['j_portainer.volume'].search([
                        ('server_id', '=', self.id),
                        ('environment_id', '=', endpoint_id),
                        ('name', '=', volume_name)
                    ], limit=1)
                    
                    # Get detailed info for this volume
                    details_response = self._make_api_request(
                        f'/api/endpoints/{endpoint_id}/docker/volumes/{volume_name}', 'GET')
                    
                    details = details_response.json() if details_response.status_code == 200 else {}
                    
                    # Prepare volume data
                    volume_data = {
                        'server_id': self.id,
                        'environment_id': endpoint_id,
                        'environment_name': env.name,
                        'name': volume_name,
                        'driver': volume.get('Driver', ''),
                        'mountpoint': volume.get('Mountpoint', ''),
                        'scope': volume.get('Scope', 'local'),
                        'labels': json.dumps(volume.get('Labels', {})),
                        'details': json.dumps(details, indent=2) if details else '',
                    }
                    
                    if existing_volume:
                        # Update existing volume - don't update created date for existing records
                        existing_volume.write(volume_data)
                        updated_count += 1
                    else:
                        # Create new volume record - set created date
                        volume_data['created'] = datetime.now()  # Docker volumes don't have created date
                        self.env['j_portainer.volume'].create(volume_data)
                        created_count += 1
                    
                    synced_volume_names.append((endpoint_id, volume_name))
                    volume_count += 1
            
            # Log the statistics
            _logger.info(f"Volume sync complete: {volume_count} total volumes, {created_count} created, {updated_count} updated")
            
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
            # Keep track of synced networks
            synced_network_ids = []
            
            # Get environments to sync
            if environment_id:
                environments = self.environment_ids.filtered(lambda e: e.environment_id == environment_id)
            else:
                environments = self.environment_ids
            
            network_count = 0
            updated_count = 0
            created_count = 0
            
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
                    
                    # Check if this network already exists in Odoo
                    existing_network = self.env['j_portainer.network'].search([
                        ('server_id', '=', self.id),
                        ('environment_id', '=', endpoint_id),
                        ('network_id', '=', network_id)
                    ], limit=1)
                    
                    # Get detailed info for this network
                    details_response = self._make_api_request(
                        f'/api/endpoints/{endpoint_id}/docker/networks/{network_id}', 'GET')
                    
                    details = details_response.json() if details_response.status_code == 200 else {}
                    
                    # Prepare network data
                    network_data = {
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
                    }
                    
                    if existing_network:
                        # Update existing network record
                        existing_network.write(network_data)
                        updated_count += 1
                    else:
                        # Create new network record
                        self.env['j_portainer.network'].create(network_data)
                        created_count += 1
                    
                    synced_network_ids.append((endpoint_id, network_id))
                    network_count += 1
            
            # Log the statistics
            _logger.info(f"Network sync complete: {network_count} total networks, {created_count} created, {updated_count} updated")
            
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
    
    def sync_standard_templates(self):
        """Sync standard application templates from Portainer"""
        self.ensure_one()
        
        try:
            # Keep track of synced templates
            synced_template_ids = []
            
            # Get templates
            response = self._make_api_request('/api/templates', 'GET')
            
            if response.status_code != 200:
                raise UserError(_("Failed to get templates: %s") % response.text)
                
            # Parse the response - it could be a dict with 'templates' key or a direct array
            response_data = response.json()
            templates = []
            
            if isinstance(response_data, dict) and 'templates' in response_data:
                # New API format: {"version": "2", "templates": [...]}
                templates = response_data.get('templates', [])
                _logger.info(f"Using template list from 'templates' key, found {len(templates)} templates")
            elif isinstance(response_data, list):
                # Old API format: direct array of templates
                templates = response_data
                _logger.info(f"Using direct template list, found {len(templates)} templates")
            else:
                _logger.warning(f"Unexpected template response format: {type(response_data)}")
                if isinstance(response_data, dict):
                    _logger.warning(f"Template response keys: {list(response_data.keys())}")
                templates = []
            
            template_count = 0
            updated_count = 0
            created_count = 0
            
            for template in templates:
                # Skip if template is not a dictionary (sometimes API returns strings)
                if not isinstance(template, dict):
                    _logger.warning(f"Skipping non-dict template: {template}")
                    continue
                
                template_id = template.get('id')
                
                # Check if this template already exists in Odoo
                existing_template = False
                if template_id:
                    existing_template = self.env['j_portainer.template'].search([
                        ('server_id', '=', self.id),
                        ('template_id', '=', template_id)
                    ], limit=1)
                
                # Prepare template data
                template_data = {
                    'server_id': self.id,
                    'title': template.get('title', ''),
                    'description': template.get('description', ''),
                    'template_type': str(template.get('type', 1)),  # 1 = container, 2 = stack
                    'platform': template.get('platform', 'linux'),
                    'template_id': template_id,
                    'logo': template.get('logo', ''),
                    'registry': template.get('registry', ''),
                    'image': template.get('image', ''),
                    'repository': json.dumps(template.get('repository', {})) if isinstance(template.get('repository', {}), dict) else '',
                    'categories': ','.join(template.get('categories', [])) if isinstance(template.get('categories', []), list) else '',
                    'environment_variables': json.dumps(template.get('env', [])),
                    'volumes': json.dumps(template.get('volumes', [])),
                    'ports': json.dumps(template.get('ports', [])),
                    'note': template.get('note', ''),
                    'is_custom': False,
                    'details': json.dumps(template, indent=2),
                }
                
                if existing_template:
                    # Update existing template
                    existing_template.write(template_data)
                    updated_count += 1
                else:
                    # Create new template - skip Portainer creation since we're just syncing
                    template_data['skip_portainer_create'] = True
                    self.env['j_portainer.template'].create(template_data)
                    created_count += 1
                
                if isinstance(template_id, (int, str)) and str(template_id).isdigit():
                    synced_template_ids.append(int(template_id))
                template_count += 1
            
            # Clean up templates that no longer exist in Portainer
            # Get all standard templates for this server
            all_templates = self.env['j_portainer.template'].search([
                ('server_id', '=', self.id),
                ('is_custom', '=', False)
            ])
            
            # Make sure all IDs are integers for proper comparison
            synced_ids = []
            for template_id in synced_template_ids:
                if isinstance(template_id, int) or (isinstance(template_id, str) and template_id.isdigit()):
                    synced_ids.append(int(template_id))
            
            # Templates to remove - those not in synced_template_ids
            # Handle template_id type conversion for comparison (some might be strings, some integers)
            templates_to_remove = all_templates.filtered(
                lambda t: (int(t.template_id) not in synced_ids) if t.template_id else True
            )
            
            # Remove obsolete templates
            if templates_to_remove:
                removed_count = len(templates_to_remove)
                _logger.info(f"Removing {removed_count} obsolete standard templates")
                templates_to_remove.unlink()
            else:
                removed_count = 0
            
            # Log the statistics
            _logger.info(f"Standard template sync complete: {template_count} total templates, {created_count} created, {updated_count} updated, {removed_count} removed")
            
            self.write({'last_sync': fields.Datetime.now()})
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Standard Templates Synchronized'),
                    'message': _('%d standard templates found, %d removed') % (template_count, removed_count),
                    'sticky': False,
                    'type': 'success',
                }
            }
            
        except Exception as e:
            _logger.error(f"Error syncing standard templates: {str(e)}")
            raise UserError(_("Error syncing standard templates: %s") % str(e))
    
    def sync_custom_templates(self):
        """Sync custom templates from Portainer"""
        self.ensure_one()
        
        try:
            # Keep track of synced custom template IDs
            synced_template_ids = []
            
            # For statistics
            template_count = 0
            updated_count = 0
            created_count = 0
            
            # Don't try to create templates in Portainer, just sync existing ones
            # We'll use skip_portainer_create flag for this
            
            # Get custom templates - try different API endpoints for different Portainer versions
            custom_templates = []
            custom_response = None
            
            # Try primary endpoint for Portainer CE 2.9.0+
            try:
                custom_response = self._make_api_request('/api/custom_templates', 'GET')
                if custom_response.status_code == 200:
                    data = custom_response.json()
                    # Handle both array and object with templates array format
                    if isinstance(data, list):
                        custom_templates = data
                    elif isinstance(data, dict) and 'templates' in data:
                        custom_templates = data['templates']
                    else:
                        _logger.info(f"Custom templates data has unexpected format: {data}")
                elif custom_response.status_code == 404:
                    _logger.info("Primary custom templates endpoint not found. Trying alternative endpoint.")
                else:
                    _logger.warning(f"Failed to get custom templates from primary endpoint: {custom_response.status_code}")
            except Exception as e:
                _logger.error(f"Error getting custom templates from primary endpoint: {str(e)}")
            
            # If primary endpoint failed, try alternative endpoint for older versions
            if not custom_templates and (custom_response is None or custom_response.status_code != 200):
                try:
                    alt_response = self._make_api_request('/api/templates/custom', 'GET')
                    if alt_response.status_code == 200:
                        data = alt_response.json()
                        # Handle both array and object formats
                        if isinstance(data, list):
                            custom_templates = data
                        elif isinstance(data, dict) and 'templates' in data:
                            custom_templates = data['templates']
                    else:
                        _logger.warning(f"Failed to get custom templates from alternative endpoint: {alt_response.status_code}")
                except Exception as e:
                    _logger.error(f"Error getting custom templates from alternative endpoint: {str(e)}")
            
            # Process custom templates
            for template in custom_templates:
                # Skip if template is not a dictionary (sometimes API returns strings)
                if not isinstance(template, dict):
                    _logger.warning(f"Skipping non-dict custom template: {template}")
                    continue
                
                # Function to get field value regardless of capitalization
                def get_field_value(data, field_names, default=None):
                    """Get a field value from a dict using multiple possible field names in any capitalization"""
                    # Try exact matches first
                    for name in field_names:
                        if name in data:
                            return data[name]
                    
                    # Try case-insensitive matches
                    lowercase_data = {k.lower(): v for k, v in data.items()}
                    for name in field_names:
                        if name.lower() in lowercase_data:
                            return lowercase_data[name.lower()]
                    
                    return default
                
                # Handle different ID field names with case insensitivity
                template_id = get_field_value(template, ['id', 'Id', 'ID'])
                
                # Check if this custom template already exists in Odoo
                existing_template = False
                if template_id:
                    existing_template = self.env['j_portainer.customtemplate'].search([
                        ('server_id', '=', self.id),
                        ('template_id', '=', template_id)
                    ], limit=1)
                
                # Platform mapping function to handle numeric values
                def map_platform(platform_value):
                    """Map platform value to appropriate string value"""
                    if isinstance(platform_value, int) or (isinstance(platform_value, str) and platform_value.isdigit()):
                        # Portainer sometimes uses numeric values for platform
                        platform_map = {
                            '1': 'linux',
                            '2': 'windows',
                            1: 'linux',
                            2: 'windows'
                        }
                        return platform_map.get(platform_value, 'linux')
                    elif isinstance(platform_value, str):
                        # If it's already a string like 'linux' or 'windows', use it directly
                        if platform_value.lower() in ['linux', 'windows']:
                            return platform_value.lower()
                    # Default fallback
                    return 'linux'
                
                # Get platform value with case-insensitive lookup
                platform_value = get_field_value(template, ['Platform', 'platform'])
                
                # Prepare custom template data with case-insensitive field extraction
                template_data = {
                    'server_id': self.id,
                    'title': get_field_value(template, ['Title', 'title'], ''),
                    'description': get_field_value(template, ['Description', 'description'], ''),
                    'template_type': str(get_field_value(template, ['Type', 'type'], 1)),
                    'platform': map_platform(platform_value),
                    'template_id': template_id,
                    'logo': get_field_value(template, ['Logo', 'logo'], ''),
                    'image': get_field_value(template, ['Image', 'image'], ''),
                    'repository': json.dumps(get_field_value(template, ['Repository', 'repository'], {})) if isinstance(get_field_value(template, ['Repository', 'repository'], {}), dict) else '',
                    'categories': ','.join(get_field_value(template, ['Categories', 'categories'], [])) if isinstance(get_field_value(template, ['Categories', 'categories'], []), list) else '',
                    'environment_variables': json.dumps(get_field_value(template, ['Env', 'env'], [])),
                    'volumes': json.dumps(get_field_value(template, ['Volumes', 'volumes'], [])),
                    'ports': json.dumps(get_field_value(template, ['Ports', 'ports'], [])),
                    'note': get_field_value(template, ['Note', 'note'], ''),
                    'is_custom': True,
                    'details': json.dumps(template, indent=2),
                    # Additional fields from Portainer with case-insensitive lookup
                    'project_path': get_field_value(template, ['ProjectPath', 'projectPath', 'projectpath'], ''),
                    'entry_point': get_field_value(template, ['EntryPoint', 'entryPoint', 'entrypoint'], ''),
                    'created_by_user_id': get_field_value(template, ['CreatedByUserId', 'createdByUserId', 'createdbyuserid'], 0),
                    'registry_url': get_field_value(template, ['Registry', 'registry'], ''),
                }
                
                # Add Git repository information if available
                repo_url = get_field_value(template, ['repositoryURL', 'RepositoryURL'])
                if repo_url:
                    template_data['build_method'] = 'repository'
                    template_data['git_repository_url'] = repo_url
                    template_data['git_repository_reference'] = get_field_value(template, ['repositoryReferenceName', 'RepositoryReferenceName'], '')
                    template_data['git_compose_path'] = get_field_value(template, ['composeFilePath', 'ComposeFilePath'], '')
                    template_data['git_skip_tls'] = get_field_value(template, ['skipTLSVerify', 'SkipTLSVerify'], False)
                    template_data['git_authentication'] = get_field_value(template, ['repositoryAuthentication', 'RepositoryAuthentication'], False)
                elif get_field_value(template, ['composeFileContent', 'ComposeFileContent']):
                    template_data['build_method'] = 'editor'
                    template_data['compose_file'] = get_field_value(template, ['composeFileContent', 'ComposeFileContent'], '')
                
                if existing_template:
                    # Update existing custom template
                    existing_template.write(template_data)
                    updated_count += 1
                else:
                    # Create new custom template - skip Portainer creation since we're just syncing
                    template_data['skip_portainer_create'] = True
                    self.env['j_portainer.customtemplate'].create(template_data)
                    created_count += 1
                
                if isinstance(template_id, (int, str)) and str(template_id).isdigit():
                    synced_template_ids.append(int(template_id))
                template_count += 1
            
            # Clean up custom templates that no longer exist in Portainer
            # Get all custom templates for this server
            all_custom_templates = self.env['j_portainer.customtemplate'].search([
                ('server_id', '=', self.id)
            ])
            
            # Make sure all IDs are integers for proper comparison
            synced_ids = []
            for template_id in synced_template_ids:
                if isinstance(template_id, int) or (isinstance(template_id, str) and template_id.isdigit()):
                    synced_ids.append(int(template_id))
            
            # Templates to remove - those not in synced_template_ids
            # Handle template_id type conversion for comparison (some might be strings, some integers)
            templates_to_remove = all_custom_templates.filtered(
                lambda t: (int(t.template_id) not in synced_ids) if t.template_id else True
            )
            
            # Remove obsolete custom templates
            if templates_to_remove:
                removed_count = len(templates_to_remove)
                _logger.info(f"Removing {removed_count} obsolete custom templates")
                templates_to_remove.unlink()
            else:
                removed_count = 0
            
            # Log the statistics
            _logger.info(f"Custom template sync complete: {template_count} total custom templates, {created_count} created, {updated_count} updated, {removed_count} removed")
            
            self.write({'last_sync': fields.Datetime.now()})
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Custom Templates Synchronized'),
                    'message': _('%d custom templates found, %d removed') % (template_count, removed_count),
                    'sticky': False,
                    'type': 'success',
                }
            }
            
        except Exception as e:
            _logger.error(f"Error syncing custom templates: {str(e)}")
            raise UserError(_("Error syncing custom templates: %s") % str(e))
            
    def sync_templates(self):
        """Sync all templates (standard and custom) from Portainer"""
        self.ensure_one()
        
        try:
            # First sync standard templates
            self.sync_standard_templates()
            
            # Then sync custom templates
            self.sync_custom_templates()
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('All Templates Synchronized'),
                    'message': _('Both standard and custom templates have been synchronized.'),
                    'sticky': False,
                    'type': 'success',
                }
            }
            
        except Exception as e:
            _logger.error(f"Error syncing all templates: {str(e)}")
            raise UserError(_("Error syncing all templates: %s") % str(e))
            
    def sync_stacks(self, environment_id=None):
        """Sync stacks from Portainer
        
        Args:
            environment_id (int, optional): Environment ID to sync stacks for.
                If not provided, syncs stacks for all environments.
        """
        self.ensure_one()
        
        try:
            # Keep track of synced stacks
            synced_stack_ids = []
            
            # Get environments to sync
            if environment_id:
                environments = self.environment_ids.filtered(lambda e: e.environment_id == environment_id)
            else:
                environments = self.environment_ids
            
            stack_count = 0
            updated_count = 0
            created_count = 0
            
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
                    
                    # Check if this stack already exists in Odoo
                    existing_stack = self.env['j_portainer.stack'].search([
                        ('server_id', '=', self.id),
                        ('environment_id', '=', endpoint_id),
                        ('stack_id', '=', stack_id)
                    ], limit=1)
                    
                    # Get stack file content if available
                    file_content = ''
                    file_response = self._make_api_request(f'/api/stacks/{stack_id}/file', 'GET')
                    if file_response.status_code == 200:
                        file_data = file_response.json()
                        file_content = file_data.get('StackFileContent', '')
                    
                    # Prepare stack data
                    stack_data = {
                        'server_id': self.id,
                        'environment_id': endpoint_id,
                        'environment_name': env.name,
                        'stack_id': stack_id,
                        'name': stack.get('Name', ''),
                        'type': str(stack.get('Type', 1)),
                        'status': str(stack.get('Status', 0)),
                        'update_date': self._parse_date_value(stack.get('UpdateDate')),
                        'file_content': file_content,
                        'details': json.dumps(stack, indent=2),
                    }
                    
                    if existing_stack:
                        # Update existing stack - don't update creation date for existing records
                        existing_stack.write(stack_data)
                        updated_count += 1
                    else:
                        # Create new stack record - set creation date
                        stack_data['creation_date'] = self._parse_date_value(stack.get('CreationDate')) or datetime.now()
                        self.env['j_portainer.stack'].create(stack_data)
                        created_count += 1
                    
                    synced_stack_ids.append((endpoint_id, stack_id))
                    stack_count += 1
            
            # Log the statistics
            _logger.info(f"Stack sync complete: {stack_count} total stacks, {created_count} created, {updated_count} updated")
            
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
            self.sync_standard_templates()
            self.sync_custom_templates()
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