#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models
import logging
import json

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
    
    def image_action(self, server_id, action, image_id=None, environment_id=None, endpoint=None, params=None):
        """Perform action on an image
        
        Args:
            server_id (int): ID of the Portainer server
            action (str): Action to perform (pull, delete, inspect, etc.)
            image_id (str, optional): Image ID or name
            environment_id (int, optional): ID of the environment
            endpoint (str, optional): Custom API endpoint to use (overrides default endpoints)
            params (dict, optional): Additional parameters
            
        Returns:
            dict or bool: API response if successful, False if failed
        """
        server = self.env['j_portainer.server'].browse(server_id)
        if not server:
            return {'error': 'Server not found'}
        
        # Use custom endpoint if provided, otherwise build standard endpoints
        if endpoint:
            api_endpoint = f'/api{endpoint}' if not endpoint.startswith('/api') else endpoint
        elif action == 'pull' and environment_id:
            api_endpoint = f'/api/endpoints/{environment_id}/docker/images/create'
        elif action in ['delete', 'remove'] and environment_id and image_id:
            api_endpoint = f'/api/endpoints/{environment_id}/docker/images/{image_id}'
        elif action == 'inspect' and environment_id and image_id:
            api_endpoint = f'/api/endpoints/{environment_id}/docker/images/{image_id}/json'
        else:
            return {'error': f'Invalid action or missing parameters: {action}'}
        
        try:
            # Handle different actions
            if action == 'pull':
                # For pull, image_id is actually the image name
                query_params = {}
                if params:
                    if 'fromImage' in params:
                        query_params['fromImage'] = params['fromImage']
                    if 'tag' in params:
                        query_params['tag'] = params['tag']
                
                response = server._make_api_request(api_endpoint, 'POST', params=query_params)
                if response.status_code in [200, 201, 204]:
                    return True
                return {'error': f'API error: {response.status_code} - {response.text}'}
                
            elif action in ['delete', 'remove']:
                query_params = {}
                if params:
                    if 'force' in params:
                        query_params['force'] = params['force']
                    if 'noprune' in params:
                        query_params['noprune'] = params['noprune']
                
                response = server._make_api_request(api_endpoint, 'DELETE', params=query_params)
                if response.status_code in [200, 201, 204]:
                    return True
                return {'error': f'API error: {response.status_code} - {response.text}'}
                
            elif action == 'inspect':
                response = server._make_api_request(api_endpoint, 'GET')
                if response.status_code == 200:
                    try:
                        return response.json()
                    except Exception as e:
                        return {'error': f'Failed to parse response: {str(e)}'}
                return {'error': f'API error: {response.status_code} - {response.text}'}
                
            return {'error': f'Unsupported action: {action}'}
            
        except Exception as e:
            return {'error': str(e)}
    
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
            
    def deploy_template(self, server_id, template_id, environment_id, params=None, is_custom=False):
        """Deploy a template (standard or custom)
        
        Args:
            server_id (int): ID of the Portainer server
            template_id (int or str): Template ID
            environment_id (int): Environment ID
            params (dict, optional): Additional parameters for deployment
            is_custom (bool): Whether this is a custom template (True) or standard template (False)
            
        Returns:
            dict: Deployment result or False if failed
        """
        server = self.env['j_portainer.server'].browse(server_id)
        if not server:
            _logger.error("Server not found")
            return False
            
        if not environment_id:
            _logger.error("Environment ID is required")
            return False
            
        # Prepare the request
        if is_custom:
            # Custom template deployment
            endpoint = f'/api/templates/custom/{template_id}'
            method = 'POST'
        else:
            # Standard template deployment
            endpoint = f'/api/templates/{template_id}'
            method = 'POST'
            
        # Prepare the request data
        data = {
            'endpointId': environment_id
        }
        
        # Add additional parameters
        if params:
            for key, value in params.items():
                data[key] = value
                
        _logger.info(f"Deploying {'custom' if is_custom else 'standard'} template with data: {json.dumps(data, indent=2)}")
        
        # Make the API request
        try:
            response = server._make_api_request(endpoint, method, data=data)
            
            if response.status_code in [200, 201, 204]:
                try:
                    return response.json()
                except:
                    return {'success': True, 'message': 'Deployment successful (no response data)'}
            else:
                _logger.error(f"Deployment failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            _logger.error(f"Error deploying template: {str(e)}")
            return False
    
    def create_template(self, server_id, template_data):
        """Create a custom template in Portainer
        
        Args:
            server_id (int): ID of the Portainer server
            template_data (dict): Template data
            
        Returns:
            dict: Created template data or None if failed
        """
        server = self.env['j_portainer.server'].browse(server_id)
        if not server:
            return None
            
        # Validate required fields
        if not template_data.get('title'):
            template_data['title'] = 'Custom Template'
        if not template_data.get('description'):
            template_data['description'] = 'Custom template created from Odoo'
        
        # Normalize type field - ensure it's an integer
        if 'type' in template_data and isinstance(template_data['type'], str):
            try:
                template_data['type'] = int(template_data['type'])
            except ValueError:
                template_data['type'] = 1  # Default to container type
        
        # Log the template data for debugging
        _logger.info(f"Creating template with data: {json.dumps(template_data, indent=2)}")
            
        # Try the v2 API endpoint first (Portainer CE 2.9.0+)
        endpoint = '/api/custom_templates'
        
        try:
            # Properly set Content-Type header
            headers = {'Content-Type': 'application/json'}
            
            # Check Portainer version to determine correct API format
            version_response = server._make_api_request('/api/system/version', 'GET')
            version_str = ''
            
            if version_response.status_code == 200:
                try:
                    version_info = version_response.json()
                    version_str = version_info.get('Version', '')
                    _logger.info(f"Detected Portainer version: {version_str}")
                except Exception as e:
                    _logger.warning(f"Error parsing version info: {str(e)}")
            
            # Prepare API-specific data format
            api_data = dict(template_data)  # Make a copy to avoid modifying the original
            
            # Get auth token to see if we need to handle it specially
            # This is used for version-specific handling if needed
            api_key = server._get_api_key_header()
            
            # Special case for Portainer CE 2.9+ and 2.17+
            if "2.9." in version_str or "2.1" in version_str or "2.2" in version_str:
                _logger.info("Using Portainer CE 2.9+ or 2.17+ format")
                # Make sure type is an integer
                if 'type' in api_data:
                    api_data['type'] = int(api_data['type'])
                
            # Special handling for Portainer CE 2.27 LTS
            if "2.27" in version_str:
                _logger.info("Using Portainer CE 2.27 LTS format")
                # Additional fields required for 2.27
                if api_data.get('type') == 2:  # Stack template
                    # Ensure required fields for stack templates
                    if 'repository' not in api_data and 'repositoryURL' in api_data:
                        api_data['repository'] = {
                            'url': api_data.get('repositoryURL', ''),
                            'stackfile': api_data.get('composeFilePath', 'docker-compose.yml')
                        }
                        if 'repositoryReferenceName' in api_data:
                            api_data['repository']['reference'] = api_data.get('repositoryReferenceName')
            
            # First try standard endpoint
            response = server._make_api_request(endpoint, 'POST', data=api_data, headers=headers)
            
            if response.status_code in [200, 201, 204]:
                try:
                    result = response.json()
                    _logger.info(f"Template created successfully with ID: {result.get('Id', 'N/A')}")
                    return result
                except Exception as e:
                    _logger.error(f"Error parsing response: {str(e)}")
                    if response.text:
                        _logger.info(f"Raw response: {response.text}")
                    return {'Id': 0}  # Return minimal success response
            else:
                # If first attempt fails, try alternative endpoint
                _logger.warning(f"Primary endpoint failed: {response.status_code} - {response.text}. Trying alternative endpoint.")
                alt_endpoint = '/api/templates/custom'
                
                # For some Portainer versions, we need to wrap the template in a templates array
                if response.status_code == 400 and "templates" not in api_data:
                    wrapped_data = {"templates": [api_data]}
                    _logger.info(f"Trying with wrapped format: {json.dumps(wrapped_data, indent=2)}")
                    alt_response = server._make_api_request(alt_endpoint, 'POST', data=wrapped_data, headers=headers)
                else:
                    alt_response = server._make_api_request(alt_endpoint, 'POST', data=api_data, headers=headers)
                
                if alt_response.status_code in [200, 201, 204]:
                    try:
                        result = alt_response.json()
                        _logger.info(f"Template created successfully with alternative endpoint. Response: {result}")
                        return result
                    except Exception as e:
                        _logger.error(f"Error parsing alternative response: {str(e)}")
                        if alt_response.text:
                            _logger.info(f"Raw response from alternative endpoint: {alt_response.text}")
                        return {'Id': 0}  # Return minimal success response
                else:
                    # Last attempt: try with templates array format directly on primary endpoint
                    if alt_response.status_code not in [200, 201, 204]:
                        wrapped_data = {"version": "2", "templates": [api_data]}
                        _logger.info(f"Trying with v2 format on primary endpoint: {endpoint}")
                        wrapped_response = server._make_api_request(endpoint, 'POST', data=wrapped_data, headers=headers)
                        
                        if wrapped_response.status_code in [200, 201, 204]:
                            try:
                                result = wrapped_response.json()
                                _logger.info(f"Template created successfully with wrapped format. Response: {result}")
                                return result
                            except Exception as e:
                                _logger.error(f"Error parsing wrapped response: {str(e)}")
                                if wrapped_response.text:
                                    _logger.info(f"Raw response from wrapped format: {wrapped_response.text}")
                                return {'Id': 0}
                    
                    _logger.error(f"Error creating template on all endpoints. Last error: {alt_response.status_code} - {alt_response.text}")
                    
                    # Check if the feature is available at all
                    version_endpoint = '/api/custom_templates'
                    version_check = server._make_api_request(version_endpoint, 'GET')
                    if version_check.status_code == 404:
                        _logger.error("Custom templates feature not available in this Portainer version")
                    
                    return None
        except Exception as e:
            _logger.error(f"Exception during template creation: {str(e)}")
            return None