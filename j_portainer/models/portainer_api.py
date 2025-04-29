#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models
import logging

_logger = logging.getLogger(__name__)

class PortainerAPI(models.AbstractModel):
    """Abstract model for Portainer API interactions
    
    This model provides common methods for interacting with the Portainer API.
    It is meant to be used by other models, not instantiated directly.
    """
    _name = 'j_portainer.api'
    _description = 'Portainer API Client'
    
    def container_action(self, server_id, environment_id, container_id, action):
        """Perform action on a container
        
        Args:
            server_id (int): ID of the Portainer server
            environment_id (int): ID of the environment
            container_id (str): Container ID
            action (str): Action to perform (start, stop, restart, kill, pause, unpause, etc.)
            
        Returns:
            bool: True if successful
        """
        server = self.env['j_portainer.server'].browse(server_id)
        if not server:
            return False
            
        endpoint = f'/api/endpoints/{environment_id}/docker/containers/{container_id}/{action}'
        response = server._make_api_request(endpoint, 'POST')
        
        return response.status_code in [200, 201, 204]
    
    def remove_container(self, server_id, environment_id, container_id, force=False, volumes=False):
        """Remove a container
        
        Args:
            server_id (int): ID of the Portainer server
            environment_id (int): ID of the environment
            container_id (str): Container ID
            force (bool): Force removal
            volumes (bool): Remove associated volumes
            
        Returns:
            dict: Result with 'success' boolean and 'message' string
        """
        server = self.env['j_portainer.server'].browse(server_id)
        if not server:
            return {'success': False, 'message': 'Server not found'}
            
        params = {
            'force': force,
            'v': volumes
        }
        
        endpoint = f'/api/endpoints/{environment_id}/docker/containers/{container_id}'
        
        try:
            response = server._make_api_request(endpoint, 'DELETE', params=params)
            
            if response.status_code in [200, 201, 204]:
                return {'success': True, 'message': 'Container removed successfully'}
            else:
                # Try to extract error message from response
                error_msg = 'Failed to remove container'
                try:
                    if response.text and len(response.text) > 0:
                        error_msg = f"{error_msg}: {response.text}"
                except:
                    pass
                    
                return {'success': False, 'message': error_msg}
        except Exception as e:
            return {'success': False, 'message': f'Error removing container: {str(e)}'}
    
    def image_action(self, server_id, environment_id, image_id, action, params=None):
        """Perform action on an image
        
        Args:
            server_id (int): ID of the Portainer server
            environment_id (int): ID of the environment
            image_id (str): Image ID or name
            action (str): Action to perform (pull, delete, etc.)
            params (dict, optional): Additional parameters
            
        Returns:
            bool: True if successful
        """
        server = self.env['j_portainer.server'].browse(server_id)
        if not server:
            return False
            
        if action == 'pull':
            endpoint = f'/api/endpoints/{environment_id}/docker/images/create'
            # For pull, image_id is actually the image name
            query_params = {'fromImage': image_id}
            if params and 'tag' in params:
                query_params['tag'] = params['tag']
                
            response = server._make_api_request(endpoint, 'POST', params=query_params)
            return response.status_code in [200, 201, 204]
            
        elif action == 'delete':
            endpoint = f'/api/endpoints/{environment_id}/docker/images/{image_id}'
            query_params = {}
            if params:
                if 'force' in params:
                    query_params['force'] = params['force']
                if 'noprune' in params:
                    query_params['noprune'] = params['noprune']
                    
            response = server._make_api_request(endpoint, 'DELETE', params=query_params)
            return response.status_code in [200, 201, 204]
            
        return False
    
    def volume_action(self, server_id, environment_id, volume_name, action):
        """Perform action on a volume
        
        Args:
            server_id (int): ID of the Portainer server
            environment_id (int): ID of the environment
            volume_name (str): Volume name
            action (str): Action to perform (currently only 'delete' is supported)
            
        Returns:
            bool: True if successful
        """
        server = self.env['j_portainer.server'].browse(server_id)
        if not server:
            return False
            
        if action == 'delete':
            endpoint = f'/api/endpoints/{environment_id}/docker/volumes/{volume_name}'
            response = server._make_api_request(endpoint, 'DELETE')
            return response.status_code in [200, 201, 204]
            
        return False
    
    def network_action(self, server_id, environment_id, network_id, action):
        """Perform action on a network
        
        Args:
            server_id (int): ID of the Portainer server
            environment_id (int): ID of the environment
            network_id (str): Network ID
            action (str): Action to perform (currently only 'delete' is supported)
            
        Returns:
            bool: True if successful
        """
        server = self.env['j_portainer.server'].browse(server_id)
        if not server:
            return False
            
        if action == 'delete':
            endpoint = f'/api/endpoints/{environment_id}/docker/networks/{network_id}'
            response = server._make_api_request(endpoint, 'DELETE')
            return response.status_code in [200, 201, 204]
            
        return False
        
    def prune_images(self, server_id, environment_id, filters=None):
        """Prune unused images
        
        Args:
            server_id (int): ID of the Portainer server
            environment_id (int): ID of the environment
            filters (dict, optional): Filters to apply
            
        Returns:
            dict: Pruning results including ImagesDeleted and SpaceReclaimed
        """
        server = self.env['j_portainer.server'].browse(server_id)
        if not server:
            return False
            
        endpoint = f'/api/endpoints/{environment_id}/docker/images/prune'
        params = {}
        if filters:
            params['filters'] = filters
            
        response = server._make_api_request(endpoint, 'POST', params=params)
        
        if response.status_code in [200, 201, 204]:
            try:
                return response.json()
            except Exception as e:
                return {'error': str(e)}
        
        return False
    
    def stack_action(self, server_id, stack_id, action, data=None):
        """Perform action on a stack
        
        Args:
            server_id (int): ID of the Portainer server
            stack_id (int): Stack ID
            action (str): Action to perform (delete, stop, start, etc.)
            data (dict, optional): Additional data for the action
            
        Returns:
            bool: True if successful
        """
        server = self.env['j_portainer.server'].browse(server_id)
        if not server:
            return False
            
        if action == 'delete':
            endpoint = f'/api/stacks/{stack_id}'
            response = server._make_api_request(endpoint, 'DELETE')
            return response.status_code in [200, 201, 204]
            
        elif action in ['start', 'stop']:
            endpoint = f'/api/stacks/{stack_id}/' + ('start' if action == 'start' else 'stop')
            response = server._make_api_request(endpoint, 'POST')
            return response.status_code in [200, 201, 204]
            
        elif action == 'update':
            if not data:
                return False
                
            endpoint = f'/api/stacks/{stack_id}'
            response = server._make_api_request(endpoint, 'PUT', data=data)
            return response.status_code in [200, 201, 204]
            
        return False
        
    def template_action(self, server_id, template_id, action, environment_id=None, data=None):
        """Perform action on a template
        
        Args:
            server_id (int): ID of the Portainer server
            template_id (int): Template ID
            action (str): Action to perform (deploy, delete, etc.)
            environment_id (int, optional): Environment ID (required for deploy)
            data (dict, optional): Additional data for the action
            
        Returns:
            bool: True if successful
        """
        server = self.env['j_portainer.server'].browse(server_id)
        if not server:
            return False
            
        if action == 'deploy' and environment_id and data:
            # Deploy template
            if 'type' in data and data['type'] == 2:  # Stack template
                endpoint = '/api/stacks'
                # Ensure required fields
                if 'name' not in data:
                    data['name'] = 'Deployed Stack'
                if 'endpointId' not in data:
                    data['endpointId'] = environment_id
                    
                response = server._make_api_request(endpoint, 'POST', data=data)
                return response.status_code in [200, 201, 204]
                
            else:  # Container template
                endpoint = f'/api/endpoints/{environment_id}/docker/containers/create'
                response = server._make_api_request(endpoint, 'POST', data=data)
                
                if response.status_code not in [200, 201, 204]:
                    return False
                    
                # Start the container if requested
                if data.get('start', False):
                    result = response.json()
                    container_id = result.get('Id')
                    
                    if container_id:
                        start_endpoint = f'/api/endpoints/{environment_id}/docker/containers/{container_id}/start'
                        start_response = server._make_api_request(start_endpoint, 'POST')
                        return start_response.status_code in [200, 201, 204]
                        
                return True
                
        elif action == 'delete' and template_id:
            # Delete custom template
            endpoint = f'/api/custom_templates/{template_id}'
            response = server._make_api_request(endpoint, 'DELETE')
            return response.status_code in [200, 201, 204]
            
        return False