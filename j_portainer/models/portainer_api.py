#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models
import logging
import json
import io
import uuid
import urllib.request
import urllib.parse
import yaml
import urllib.error

# Try to import optional dependencies
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    
try:
    from requests_toolbelt.multipart.encoder import MultipartEncoder
    MULTIPART_ENCODER_AVAILABLE = True
except ImportError:
    MULTIPART_ENCODER_AVAILABLE = False

_logger = logging.getLogger(__name__)

class PortainerAPI(models.AbstractModel):
    """Abstract model for Portainer API interactions
    
    This model provides common methods for interacting with the Portainer API.
    It is meant to be used by other models, not instantiated directly.
    
    Note: This implementation uses exclusively Portainer v2 API endpoints for
    compatibility with Portainer CE 2.9.0+ and especially 2.27.4 LTS.
    All legacy v1 API endpoints have been removed.
    """
    _name = 'j_portainer.api'
    _description = 'Portainer API Client'
    
    def container_action(self, server_id, environment_id, container_id, action, params=None):
        """Perform action on a container
        
        Args:
            server_id (int): ID of the Portainer server
            environment_id (int): ID of the environment
            container_id (str): Container ID
            action (str): Action to perform (start, stop, restart, kill, pause, unpause, exec, rename, etc.)
            params (dict, optional): Additional parameters for the action
            
        Returns:
            bool or dict: True if successful with no response data, or dict with response data
        """
        server = self.env['j_portainer.server'].browse(server_id)
        if not server:
            return False
        
        # Special handling for certain actions
        if action == 'exec':
            if not params:
                params = {}
            
            # Create exec instance
            exec_endpoint = f'/api/endpoints/{environment_id}/docker/containers/{container_id}/exec'
            exec_data = {
                'AttachStdout': True,
                'AttachStderr': True,
                'Tty': params.get('tty', True),
                'Cmd': params.get('cmd', ['/bin/sh'])
            }
            
            # Add additional parameters
            if 'user' in params:
                exec_data['User'] = params['user']
            if 'env' in params:
                exec_data['Env'] = params['env']
            if 'workdir' in params:
                exec_data['WorkingDir'] = params['workdir']
                
            # Create the exec instance
            response = server._make_api_request(exec_endpoint, 'POST', data=exec_data)
            
            if response.status_code != 201:
                return {'error': f'Failed to create exec instance: {response.text}'}
                
            # Get the exec ID
            exec_id = response.json().get('Id')
            if not exec_id:
                return {'error': 'No exec ID returned'}
                
            # Start the exec instance
            start_endpoint = f'/api/endpoints/{environment_id}/docker/exec/{exec_id}/start'
            start_data = {
                'Detach': params.get('detach', False),
                'Tty': params.get('tty', True)
            }
            
            start_response = server._make_api_request(start_endpoint, 'POST', data=start_data)
            
            if start_response.status_code == 200:
                # If we're in attached mode, return the output
                if not params.get('detach', False):
                    return {'success': True, 'output': start_response.text}
                return {'success': True, 'exec_id': exec_id}
            else:
                return {'error': f'Failed to start exec instance: {start_response.text}'}
        
        elif action == 'logs':
            # Get container logs
            logs_endpoint = f'/api/endpoints/{environment_id}/docker/containers/{container_id}/logs'
            query_params = {
                'stdout': 1,
                'stderr': 1
            }
            
            # Add optional parameters
            if params:
                if 'tail' in params:
                    query_params['tail'] = params['tail']
                if 'since' in params:
                    query_params['since'] = params['since']
                if 'until' in params:
                    query_params['until'] = params['until']
                if 'timestamps' in params:
                    query_params['timestamps'] = 1 if params['timestamps'] else 0
                if 'follow' in params:
                    query_params['follow'] = 1 if params['follow'] else 0
            
            response = server._make_api_request(logs_endpoint, 'GET', params=query_params, 
                                              headers={'Accept': 'text/plain'})
            
            if response.status_code == 200:
                return {'success': True, 'logs': response.text}
            else:
                return {'error': f'Failed to get logs: {response.text}'}
        
        elif action == 'rename':
            if not params or 'name' not in params:
                return {'error': 'New name is required for rename action'}
                
            rename_endpoint = f'/api/endpoints/{environment_id}/docker/containers/{container_id}/rename'
            query_params = {'name': params['name']}
            
            response = server._make_api_request(rename_endpoint, 'POST', params=query_params)
            
            return response.status_code in [200, 201, 204]
            
        elif action == 'update':
            # Update container configuration
            update_endpoint = f'/api/endpoints/{environment_id}/docker/containers/{container_id}/update'
            
            # Prepare update data
            update_data = params if params else {}
            
            response = server._make_api_request(update_endpoint, 'POST', data=update_data)
            
            if response.status_code in [200, 201, 204]:
                return response.json() if response.text else {'success': True}
            else:
                return {'error': f'Failed to update container: {response.text}'}
            
        elif action == 'inspect':
            # Get detailed container information
            inspect_endpoint = f'/api/endpoints/{environment_id}/docker/containers/{container_id}/json'
            
            query_params = {}
            if params and 'size' in params:
                query_params['size'] = params['size']
                
            response = server._make_api_request(inspect_endpoint, 'GET', params=query_params)
            
            if response.status_code == 200:
                return response.json()
            else:
                return {'error': f'Failed to inspect container: {response.text}'}

        else:
            # Standard actions: start, stop, restart, kill, pause, unpause
            endpoint = f'/api/endpoints/{environment_id}/docker/containers/{container_id}/{action}'
            query_params = params if params else {}
            response = server._make_api_request(endpoint, 'POST', params=query_params)
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
            
        # Build query parameters
        params = {
            'force': force,
            'v': volumes
        }
        
        # Create detailed request information for logging purposes
        remove_data = {
            'containerId': container_id,
            'operation': 'remove',
            'options': {
                'force': force,
                'removeVolumes': volumes
            },
            'environment_id': environment_id
        }
        
        endpoint = f'/api/endpoints/{environment_id}/docker/containers/{container_id}'
        
        try:
            # Pass both params (for URL query) and data (for logging)
            response = server._make_api_request(
                endpoint=endpoint, 
                method='DELETE', 
                params=params,
                data=remove_data  # This is for logging only as DELETE requests don't have body
            )
            
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
            action (str): Action to perform (pull, delete, inspect, tag, push, history, etc.)
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
        elif action == 'list' and environment_id:
            api_endpoint = f'/api/endpoints/{environment_id}/docker/images/json'
        elif action in ['delete', 'remove'] and environment_id and image_id:
            api_endpoint = f'/api/endpoints/{environment_id}/docker/images/{image_id}'
        elif action == 'inspect' and environment_id and image_id:
            api_endpoint = f'/api/endpoints/{environment_id}/docker/images/{image_id}/json'
        elif action == 'history' and environment_id and image_id:
            api_endpoint = f'/api/endpoints/{environment_id}/docker/images/{image_id}/history'
        elif action == 'tag' and environment_id and image_id:
            api_endpoint = f'/api/endpoints/{environment_id}/docker/images/{image_id}/tag'
        elif action == 'push' and environment_id and image_id:
            api_endpoint = f'/api/endpoints/{environment_id}/docker/images/{image_id}/push'
        elif action == 'prune' and environment_id:
            api_endpoint = f'/api/endpoints/{environment_id}/docker/images/prune'
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
                    if 'platform' in params:
                        query_params['platform'] = params['platform']
                
                response = server._make_api_request(api_endpoint, 'POST', params=query_params)
                if response.status_code in [200, 201, 204]:
                    return {'success': True, 'message': 'Image pulled successfully'}
                return {'error': f'API error: {response.status_code} - {response.text}'}
            
            elif action == 'list':
                query_params = {}
                if params:
                    if 'all' in params:
                        query_params['all'] = params['all']
                    if 'filters' in params:
                        query_params['filters'] = params['filters']
                    if 'digests' in params:
                        query_params['digests'] = params['digests']
                
                response = server._make_api_request(api_endpoint, 'GET', params=query_params)
                if response.status_code == 200:
                    try:
                        return response.json()
                    except Exception as e:
                        return {'error': f'Failed to parse response: {str(e)}'}
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
                    try:
                        # Some versions return a JSON response with deletion info
                        return response.json() 
                    except:
                        return {'success': True, 'message': 'Image removed successfully'}
                return {'error': f'API error: {response.status_code} - {response.text}'}
                
            elif action == 'inspect':
                response = server._make_api_request(api_endpoint, 'GET')
                if response.status_code == 200:
                    try:
                        return response.json()
                    except Exception as e:
                        return {'error': f'Failed to parse response: {str(e)}'}
                return {'error': f'API error: {response.status_code} - {response.text}'}
            
            elif action == 'history':
                response = server._make_api_request(api_endpoint, 'GET')
                if response.status_code == 200:
                    try:
                        return response.json()
                    except Exception as e:
                        return {'error': f'Failed to parse response: {str(e)}'}
                return {'error': f'API error: {response.status_code} - {response.text}'}
            
            elif action == 'tag':
                if not params or not params.get('repo'):
                    return {'error': 'Repository name is required for tagging'}
                
                query_params = {'repo': params['repo']}
                if 'tag' in params:
                    query_params['tag'] = params['tag']
                
                response = server._make_api_request(api_endpoint, 'POST', params=query_params)
                if response.status_code in [200, 201, 204]:
                    return {'success': True, 'message': 'Image tagged successfully'}
                return {'error': f'API error: {response.status_code} - {response.text}'}
            
            elif action == 'push':
                if not params:
                    params = {}
                
                # Check if auth credentials are provided
                headers = {}
                if 'X-Registry-Auth' in params:
                    headers['X-Registry-Auth'] = params['X-Registry-Auth']
                
                response = server._make_api_request(api_endpoint, 'POST', headers=headers)
                if response.status_code in [200, 201, 204]:
                    return {'success': True, 'message': 'Image pushed successfully'}
                return {'error': f'API error: {response.status_code} - {response.text}'}
            
            elif action == 'prune':
                query_params = {}
                if params and 'filters' in params:
                    query_params['filters'] = params['filters']
                
                response = server._make_api_request(api_endpoint, 'POST', params=query_params)
                if response.status_code in [200, 201, 204]:
                    try:
                        return response.json()  # Returns {"ImagesDeleted": [], "SpaceReclaimed": 0}
                    except Exception as e:
                        return {'success': True, 'message': 'Images pruned successfully'}
                return {'error': f'API error: {response.status_code} - {response.text}'}
                
            return {'error': f'Unsupported action: {action}'}
            
        except Exception as e:
            return {'error': str(e)}
    
    def volume_action(self, server_id, environment_id, volume_name=None, action=None, params=None):
        """Perform action on a volume
        
        Args:
            server_id (int): ID of the Portainer server
            environment_id (int): ID of the environment
            volume_name (str, optional): Volume name (required for specific volume actions)
            action (str): Action to perform (create, delete, inspect, list, prune)
            params (dict, optional): Additional parameters for the action
            
        Returns:
            dict or bool: API response data or success status
        """
        server = self.env['j_portainer.server'].browse(server_id)
        if not server:
            return {'error': 'Server not found'}
        
        if action == 'create':
            # Create a new volume
            endpoint = f'/api/endpoints/{environment_id}/docker/volumes/create'
            
            # Prepare volume data
            data = {}
            if params:
                if 'Name' in params:
                    data['Name'] = params['Name']
                if 'Driver' in params:
                    data['Driver'] = params['Driver']
                if 'DriverOpts' in params:
                    data['DriverOpts'] = params['DriverOpts']
                if 'Labels' in params:
                    data['Labels'] = params['Labels']
            
            response = server._make_api_request(endpoint, 'POST', data=data)
            if response.status_code in [201, 200]:
                try:
                    return response.json()
                except Exception as e:
                    return {'error': f'Failed to parse response: {str(e)}'}
            return {'error': f'Failed to create volume: {response.text}'}
            
        elif action == 'list':
            # List all volumes
            endpoint = f'/api/endpoints/{environment_id}/docker/volumes'
            
            # Add filters if provided
            query_params = {}
            if params and 'filters' in params:
                query_params['filters'] = params['filters']
                
            response = server._make_api_request(endpoint, 'GET', params=query_params)
            if response.status_code == 200:
                try:
                    return response.json()
                except Exception as e:
                    return {'error': f'Failed to parse response: {str(e)}'}
            return {'error': f'Failed to list volumes: {response.text}'}
            
        elif action == 'inspect' and volume_name:
            # Inspect a specific volume
            endpoint = f'/api/endpoints/{environment_id}/docker/volumes/{volume_name}'
            response = server._make_api_request(endpoint, 'GET')
            if response.status_code == 200:
                try:
                    return response.json()
                except Exception as e:
                    return {'error': f'Failed to parse response: {str(e)}'}
            return {'error': f'Failed to inspect volume: {response.text}'}
            
        elif action == 'delete' and volume_name:
            # Delete a volume
            endpoint = f'/api/endpoints/{environment_id}/docker/volumes/{volume_name}'
            
            # Add force parameter if provided
            query_params = {}
            if params and 'force' in params:
                query_params['force'] = params['force']
                
            response = server._make_api_request(endpoint, 'DELETE', params=query_params)
            if response.status_code in [200, 201, 204]:
                return {'success': True, 'message': f'Volume {volume_name} deleted successfully'}
            return {'error': f'Failed to delete volume: {response.text}'}
            
        elif action == 'prune':
            # Prune unused volumes
            endpoint = f'/api/endpoints/{environment_id}/docker/volumes/prune'
            
            # Add filters if provided
            query_params = {}
            if params and 'filters' in params:
                query_params['filters'] = params['filters']
                
            response = server._make_api_request(endpoint, 'POST', params=query_params)
            if response.status_code in [200, 201]:
                try:
                    return response.json()  # Returns {"VolumesDeleted": [], "SpaceReclaimed": 0}
                except Exception as e:
                    return {'success': True, 'message': 'Volumes pruned successfully'}
            return {'error': f'Failed to prune volumes: {response.text}'}
            
        return {'error': f'Unsupported action: {action}'}
    
    def network_action(self, server_id, environment_id, network_id=None, action=None, params=None):
        """Perform action on a network
        
        Args:
            server_id (int): ID of the Portainer server
            environment_id (int): ID of the environment
            network_id (str, optional): Network ID (required for specific network actions)
            action (str): Action to perform (create, delete, inspect, list, connect, disconnect, prune)
            params (dict, optional): Additional parameters for the action
            
        Returns:
            dict or bool: API response data or success status
        """
        server = self.env['j_portainer.server'].browse(server_id)
        if not server:
            return {'error': 'Server not found'}
        
        if action == 'list':
            # List all networks
            endpoint = f'/api/endpoints/{environment_id}/docker/networks'
            
            # Add filters if provided
            query_params = {}
            if params and 'filters' in params:
                query_params['filters'] = params['filters']
                
            response = server._make_api_request(endpoint, 'GET', params=query_params)
            if response.status_code == 200:
                try:
                    return response.json()
                except Exception as e:
                    return {'error': f'Failed to parse response: {str(e)}'}
            return {'error': f'Failed to list networks: {response.text}'}
            
        elif action == 'inspect' and network_id:
            # Inspect a specific network
            endpoint = f'/api/endpoints/{environment_id}/docker/networks/{network_id}'
            
            # Add optional parameters if provided
            query_params = {}
            if params and 'verbose' in params:
                query_params['verbose'] = params['verbose']
            if params and 'scope' in params:
                query_params['scope'] = params['scope']
                
            response = server._make_api_request(endpoint, 'GET', params=query_params)
            if response.status_code == 200:
                try:
                    return response.json()
                except Exception as e:
                    return {'error': f'Failed to parse response: {str(e)}'}
            return {'error': f'Failed to inspect network: {response.text}'}
            
        elif action == 'create':
            # Create a new network
            endpoint = f'/api/endpoints/{environment_id}/docker/networks/create'
            
            # Prepare network data
            data = {}
            if params:
                # Required parameters
                if 'Name' in params:
                    data['Name'] = params['Name']
                else:
                    return {'error': 'Network name is required for creation'}
                
                # Optional parameters
                if 'Driver' in params:
                    data['Driver'] = params['Driver']
                if 'Options' in params:
                    data['Options'] = params['Options']
                if 'IPAM' in params:
                    data['IPAM'] = params['IPAM']
                if 'Internal' in params:
                    data['Internal'] = params['Internal']
                if 'EnableIPv6' in params:
                    data['EnableIPv6'] = params['EnableIPv6']
                if 'Labels' in params:
                    data['Labels'] = params['Labels']
                if 'Attachable' in params:
                    data['Attachable'] = params['Attachable']
            else:
                return {'error': 'Network parameters are required for creation'}
            
            response = server._make_api_request(endpoint, 'POST', data=data)
            if response.status_code in [201, 200]:
                try:
                    return response.json()
                except Exception as e:
                    return {'error': f'Failed to parse response: {str(e)}'}
            return {'error': f'Failed to create network: {response.text}'}
            
        elif action == 'delete' and network_id:
            # Delete a network
            endpoint = f'/api/endpoints/{environment_id}/docker/networks/{network_id}'
            response = server._make_api_request(endpoint, 'DELETE')
            if response.status_code in [200, 201, 204]:
                return {'success': True, 'message': f'Network {network_id} deleted successfully'}
            return {'error': f'Failed to delete network: {response.text}'}
            
        elif action == 'connect' and network_id:
            # Connect a container to a network
            if not params or 'Container' not in params:
                return {'error': 'Container ID is required to connect to network'}
                
            endpoint = f'/api/endpoints/{environment_id}/docker/networks/{network_id}/connect'
            
            # Prepare connect data
            data = {'Container': params['Container']}
            
            # Optional parameters
            if 'EndpointConfig' in params:
                data['EndpointConfig'] = params['EndpointConfig']
                
            response = server._make_api_request(endpoint, 'POST', data=data)
            if response.status_code in [200, 201, 204]:
                return {'success': True, 'message': f'Container connected to network successfully'}
            return {'error': f'Failed to connect container to network: {response.text}'}
            
        elif action == 'disconnect' and network_id:
            # Disconnect a container from a network
            if not params or 'Container' not in params:
                return {'error': 'Container ID is required to disconnect from network'}
                
            endpoint = f'/api/endpoints/{environment_id}/docker/networks/{network_id}/disconnect'
            
            # Prepare disconnect data
            data = {'Container': params['Container']}
            
            # Optional parameters
            if 'Force' in params:
                data['Force'] = params['Force']
                
            response = server._make_api_request(endpoint, 'POST', data=data)
            if response.status_code in [200, 201, 204]:
                return {'success': True, 'message': f'Container disconnected from network successfully'}
            return {'error': f'Failed to disconnect container from network: {response.text}'}
            
        elif action == 'prune':
            # Prune unused networks
            endpoint = f'/api/endpoints/{environment_id}/docker/networks/prune'
            
            # Add filters if provided
            query_params = {}
            if params and 'filters' in params:
                query_params['filters'] = params['filters']
                
            response = server._make_api_request(endpoint, 'POST', params=query_params)
            if response.status_code in [200, 201]:
                try:
                    return response.json()  # Returns {"NetworksDeleted": []}
                except Exception as e:
                    return {'success': True, 'message': 'Networks pruned successfully'}
            return {'error': f'Failed to prune networks: {response.text}'}
            
        return {'error': f'Unsupported action: {action}'}
        
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
    
    def stack_action(self, server_id, stack_id, action, data=None, environment_id=None):
        """Perform action on a stack
        
        Args:
            server_id (int): ID of the Portainer server
            stack_id (int): Stack ID
            action (str): Action to perform (delete, stop, start, redeploy, etc.)
            data (dict, optional): Additional data for the action
            environment_id (int, optional): Environment ID for the stack
            
        Returns:
            bool or dict: True if successful with no response, or dict with response data
        """
        server = self.env['j_portainer.server'].browse(server_id)
        if not server:
            return {'error': 'Server not found'}
            
        if action == 'delete':
            # For deletion, we need to include the endpoint parameter to avoid the
            # "unable to find endpoint associated with stack" error
            delete_params = {}
            # If environment ID is provided, use it in query params
            if environment_id:
                delete_params['endpointId'] = environment_id
            
            endpoint = f'/api/stacks/{stack_id}'
            response = server._make_api_request(endpoint, 'DELETE', params=delete_params)
            if response.status_code in [200, 201, 204]:
                return True
            return {'error': f'Failed to delete stack: {response.text}'}
            
        elif action in ['start', 'stop']:
            # Build the correct endpoint with endpointId as part of the URL itself
            # Format: /api/stacks/{stack_id}/{start|stop}?endpointId={environment_id}
            action_endpoint = ('start' if action == 'start' else 'stop')
            
            # Portainer requires endpointId
            if not environment_id:
                return {'error': f'Environment ID is required for {action} operation'}
            
            # Build endpoint with explicit endpointId parameter
            endpoint = f'/api/stacks/{stack_id}/{action_endpoint}'
            
            # Make API request with endpointId as query parameter
            action_params = {'endpointId': str(environment_id)}
            
            _logger.info(f"Stack {action} request: endpoint={endpoint}, params={action_params}")
            
            # Make the API request with parameters properly attached as query parameters
            response = server._make_api_request(endpoint, 'POST', params=action_params)
            
            # Check for success and return appropriate response
            if response.status_code in [200, 201, 204]:
                _logger.info(f"Stack {action} successful with status code: {response.status_code}")
                return True
            
            # Log detailed error
            error_message = f"Failed to {action} stack: {response.text} (Status code: {response.status_code})"
            _logger.error(error_message)
            
            # Return detailed error information
            return {'error': error_message}
            
        elif action == 'update':
            if not data:
                return {'error': 'No data provided for stack update'}
                
            endpoint = f'/api/stacks/{stack_id}'
            response = server._make_api_request(endpoint, 'PUT', data=data)
            if response.status_code in [200, 201, 204]:
                if response.text:
                    try:
                        return response.json()
                    except:
                        return True
                return True
            return {'error': f'Failed to update stack: {response.text}'}
            
        elif action == 'redeploy':
            endpoint = f'/api/stacks/{stack_id}/git/redeploy'
            response = server._make_api_request(endpoint, 'PUT', data=data)
            if response.status_code in [200, 201, 204]:
                return True
            return {'error': f'Failed to redeploy stack: {response.text}'}
            
        elif action == 'migrate':
            if not data or 'endpointId' not in data:
                return {'error': 'Target environment ID is required for stack migration'}
                
            endpoint = f'/api/stacks/{stack_id}/migrate'
            response = server._make_api_request(endpoint, 'POST', data=data)
            if response.status_code in [200, 201, 204]:
                if response.text:
                    try:
                        return response.json()
                    except:
                        return True
                return True
            return {'error': f'Failed to migrate stack: {response.text}'}
            
        elif action == 'get_file':
            endpoint = f'/api/stacks/{stack_id}/file'
            response = server._make_api_request(endpoint, 'GET')
            if response.status_code == 200:
                try:
                    return response.json()
                except:
                    return {'content': response.text}
            return {'error': f'Failed to get stack file: {response.text}'}
            
        elif action == 'update_git':
            if not data:
                return {'error': 'No Git data provided for stack update'}
                
            endpoint = f'/api/stacks/{stack_id}/git'
            response = server._make_api_request(endpoint, 'POST', data=data)
            if response.status_code in [200, 201, 204]:
                return True
            return {'error': f'Failed to update stack Git config: {response.text}'}
            
        elif action == 'associate':
            if not data or 'endpointId' not in data:
                return {'error': 'Target environment ID is required for stack association'}
                
            endpoint = f'/api/stacks/{stack_id}/associate'
            response = server._make_api_request(endpoint, 'PUT', data=data)
            if response.status_code in [200, 201, 204]:
                return True
            return {'error': f'Failed to associate stack: {response.text}'}
            
        return {'error': f'Unsupported stack action: {action}'}
        
    def template_action(self, server_id, template_id, action, environment_id=None, data=None):
        """Perform action on a template
        
        Args:
            server_id (int): ID of the Portainer server
            template_id (int): Template ID
            action (str): Action to perform (deploy, delete, get_file, update, git_fetch)
            environment_id (int, optional): Environment ID (required for deploy)
            data (dict, optional): Additional data for the action
            
        Returns:
            dict or bool: API response data or success status
        """
        server = self.env['j_portainer.server'].browse(server_id)
        if not server:
            return {'error': 'Server not found'}
            
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
                if response.status_code in [200, 201, 204]:
                    try:
                        return response.json()
                    except:
                        return {'success': True, 'message': 'Stack deployed successfully'}
                return {'error': f'Failed to deploy stack: {response.text}'}
                
            else:  # Container template
                endpoint = f'/api/endpoints/{environment_id}/docker/containers/create'
                response = server._make_api_request(endpoint, 'POST', data=data)
                
                if response.status_code not in [200, 201, 204]:
                    return {'error': f'Failed to create container: {response.text}'}
                
                # Get the container ID from the response
                try:
                    result = response.json()
                    container_id = result.get('Id')
                    
                    # Start the container if requested
                    if data.get('start', False) and container_id:
                        start_endpoint = f'/api/endpoints/{environment_id}/docker/containers/{container_id}/start'
                        start_response = server._make_api_request(start_endpoint, 'POST')
                        
                        if start_response.status_code in [200, 201, 204]:
                            return {'success': True, 'message': 'Container created and started successfully', 'container_id': container_id}
                        else:
                            return {
                                'warning': True, 
                                'message': f'Container created but failed to start: {start_response.text}',
                                'container_id': container_id
                            }
                    
                    return {'success': True, 'message': 'Container created successfully', 'container_id': container_id}
                except Exception as e:
                    return {'warning': True, 'message': f'Container created but error processing response: {str(e)}'}
                
        elif action == 'delete' and template_id:
            # Delete custom template
            endpoint = f'/api/custom_templates/{template_id}'
            response = server._make_api_request(endpoint, 'DELETE')
            if response.status_code in [200, 201, 204]:
                return {'success': True, 'message': 'Template deleted successfully'}
            return {'error': f'Failed to delete template: {response.text}'}
            
        elif action == 'get_file' and template_id:
            # Get template file content
            endpoint = f'/api/custom_templates/{template_id}/file'
            response = server._make_api_request(endpoint, 'GET')
            if response.status_code == 200:
                try:
                    return response.json()
                except:
                    return {'content': response.text}
            return {'error': f'Failed to get template file: {response.text}'}
            
        elif action == 'update' and template_id:
            # Update custom template
            if not data:
                return {'error': 'No data provided for template update'}
                
            endpoint = f'/api/custom_templates/{template_id}'
            response = server._make_api_request(endpoint, 'PUT', data=data)
            if response.status_code in [200, 201, 204]:
                return {'success': True, 'message': 'Template updated successfully'}
            return {'error': f'Failed to update template: {response.text}'}
            
        elif action == 'git_fetch' and template_id:
            # Fetch latest content from git repository
            endpoint = f'/api/custom_templates/{template_id}/git_fetch'
            response = server._make_api_request(endpoint, 'PUT', data=data)
            if response.status_code in [200, 201, 204]:
                return {'success': True, 'message': 'Git repository fetched successfully'}
            return {'error': f'Failed to fetch from git repository: {response.text}'}
            
        return {'error': f'Unsupported action: {action}'}
            
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
            # For custom templates, we need to get the template first and then deploy based on its type
            # Get the custom template details
            template_endpoint = f'/api/custom_templates/{template_id}'
            template_response = server._make_api_request(template_endpoint, 'GET')
            
            if template_response.status_code != 200:
                _logger.error(f"Failed to get custom template details: {template_response.status_code}")
                return False
                
            template_data = template_response.json()
            template_type = template_data.get('Type', 2)  # Default to container
            
            _logger.info(f"Retrieved template data: {json.dumps(template_data, indent=2)}")
            
            # Use appropriate endpoint based on template type
            if template_type == 1:  # Swarm stack
                endpoint = f'/api/stacks'
                method = 'POST'
            else:  # Standalone container (type 2)
                # For container creation, the name goes in the URL parameter
                container_name = params.get('name', f"container-{template_id}") if params else f"container-{template_id}"
                endpoint = f'/api/endpoints/{environment_id}/docker/containers/create?name={container_name}'
                method = 'POST'
        else:
            # Standard template deployment
            endpoint = f'/api/templates/{template_id}'
            method = 'POST'
            
        # Prepare the request data
        if is_custom:
            if template_type == 1:  # Swarm stack
                data = {
                    'endpointId': environment_id,
                    'type': 1,  # Swarm stack
                    'method': 'string',  # Deploy from string content
                    'body': template_data.get('FileContent', ''),
                }
                # Add stack name from params
                if params and 'name' in params:
                    data['name'] = params['name']
            else:  # Standalone container (type 2)
                # For custom templates with ProjectPath, we need to get the file content separately
                file_content = ''
                
                if 'ProjectPath' in template_data and template_data.get('EntryPoint'):
                    # Get file content from the file endpoint
                    file_endpoint = f'/api/custom_templates/{template_id}/file'
                    file_response = server._make_api_request(file_endpoint, 'GET')
                    
                    if file_response.status_code == 200:
                        file_content = file_response.text
                        _logger.info(f"Retrieved file content from file endpoint: {len(file_content)} characters")
                        
                        # Check if the response is JSON wrapped
                        try:
                            file_json = json.loads(file_content)
                            if 'FileContent' in file_json:
                                file_content = file_json['FileContent']
                                _logger.info(f"Extracted FileContent from JSON wrapper: {len(file_content)} characters")
                        except json.JSONDecodeError:
                            # Not JSON, use as-is
                            pass
                    else:
                        _logger.warning(f"Failed to get file content: {file_response.status_code}")
                else:
                    # Try direct content fields for inline templates
                    file_content = (template_data.get('FileContent') or 
                                   template_data.get('fileContent') or 
                                   template_data.get('file_content') or 
                                   template_data.get('body') or '')
                    _logger.info(f"Using inline content: {len(file_content)} characters")
                
                if not file_content:
                    raise Exception(f"Custom template {template_id} has no accessible file content to deploy")
                
                # Debug: Show the actual file content
                _logger.info(f"Template file content preview: {file_content[:500]}...")
                
                # Try to extract image from file content
                image = None
                try:
                    compose_data = yaml.safe_load(file_content)
                    _logger.info(f"Parsed YAML data: {compose_data}")
                    
                    # Handle different formats
                    if isinstance(compose_data, dict):
                        # Standard docker-compose format with services
                        if 'services' in compose_data:
                            first_service = next(iter(compose_data['services'].values()))
                            image = first_service.get('image')
                        # Single service format (just the service definition)
                        elif 'image' in compose_data:
                            image = compose_data['image']
                        # Check if it's a direct image specification
                        else:
                            # Look for any image field in the structure
                            for key, value in compose_data.items():
                                if key.lower() == 'image' or (isinstance(value, dict) and 'image' in value):
                                    image = value if isinstance(value, str) else value.get('image')
                                    break
                    
                    if not image:
                        raise Exception(f"No image found in template. Content structure: {list(compose_data.keys()) if isinstance(compose_data, dict) else type(compose_data)}")
                        
                except yaml.YAMLError as e:
                    # If YAML parsing fails, try to extract image from text
                    _logger.warning(f"YAML parsing failed: {e}, trying text extraction")
                    import re
                    image_match = re.search(r'image:\s*([^\s\n]+)', file_content, re.IGNORECASE)
                    if image_match:
                        image = image_match.group(1)
                    else:
                        raise Exception(f"Failed to parse template file content and no image found in text: {str(e)}")
                
                # For container deployment, we need to format according to Docker API
                # Note: name is now in URL parameter, not in body
                data = {
                    'Image': image,
                }
                
                # Add restart policy if provided
                if params and 'RestartPolicy' in params:
                    data['HostConfig'] = {
                        'RestartPolicy': params['RestartPolicy']
                    }
        else:
            # Standard template deployment
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
                error_message = f"Deployment failed (HTTP {response.status_code})"
                try:
                    error_data = response.json()
                    if 'message' in error_data:
                        error_message = error_data['message']
                except:
                    if response.text:
                        error_message = response.text
                
                _logger.error(f"Deployment failed: {response.status_code} - {response.text}")
                # Raise exception so it reaches the user interface
                raise Exception(error_message)
        except Exception as e:
            _logger.error(f"Error deploying template: {str(e)}")
            # Re-raise the exception so it reaches the user interface
            raise
    
    def execute_container_command(self, server_id, container_id, environment_id, command):
        """
        Execute a command inside a running container using Docker exec API
        For size checking commands, automatically tries fallback commands if the primary fails
        
        Args:
            server_id (int): ID of the Portainer server
            container_id (str): Container ID in Portainer
            environment_id (int): Environment ID
            command (str): Command to execute (e.g., "du -sh /mnt/data")
            
        Returns:
            str: Command output or None if failed
        """
        server = self.env['j_portainer.server'].browse(server_id)
        if not server:
            _logger.error("Server not found")
            return None
            
        if not environment_id or not container_id:
            _logger.error("Environment ID and Container ID are required")
            return None

        # Check if this is a size checking command and prepare fallback commands
        is_size_command = command.startswith('du -sh')
        commands_to_try = [command]
        
        if is_size_command:
            # Extract the path from the du command
            path = command.replace('du -sh ', '').strip()
            commands_to_try = [
                f'du -sh {path}',
                f'find {path} -type f -exec ls -l {{}} \\; | awk "{{sum+=$5}} END {{print sum \\"bytes\\"}}"',
                f'ls -la {path}'
            ]
            
        # Try each command until one succeeds
        for cmd in commands_to_try:
            try:
                result = self._execute_single_command(server, environment_id, container_id, cmd)
                if result and not self._is_command_not_found_error(result):
                    # Command succeeded, return the result
                    if cmd != command:
                        _logger.info(f"Fallback command succeeded: {cmd}")
                    return result
                elif result:
                    # Command failed with "not found" error, try next fallback
                    _logger.warning(f"Command '{cmd}' not available, trying fallback")
                    continue
                else:
                    # Command execution failed completely, try next fallback
                    continue
                    
            except Exception as e:
                _logger.warning(f"Command '{cmd}' failed with exception: {str(e)}")
                continue
        
        # All commands failed
        _logger.error(f"All commands failed for size check on path: {command}")
        return None
        
    def _execute_single_command(self, server, environment_id, container_id, command):
        """Execute a single command in container"""
        try:
            # Step 1: Create exec instance in the container
            exec_endpoint = f'/api/endpoints/{environment_id}/docker/containers/{container_id}/exec'
            exec_data = {
                'AttachStdout': True,
                'AttachStderr': True,
                'Cmd': command.split(),
                'Tty': False
            }
            
            exec_response = server._make_api_request(exec_endpoint, 'POST', data=exec_data)
            
            if exec_response.status_code != 201:
                return None
                
            exec_result = exec_response.json()
            exec_id = exec_result.get('Id')
            
            if not exec_id:
                return None
                
            # Step 2: Start the exec instance and capture output
            start_endpoint = f'/api/endpoints/{environment_id}/docker/exec/{exec_id}/start'
            start_data = {
                'Detach': False,
                'Tty': False
            }
            
            start_response = server._make_api_request(start_endpoint, 'POST', data=start_data)
            
            if start_response.status_code == 200:
                return start_response.text.strip()
            else:
                return None
                
        except Exception as e:
            return None
            
    def _is_command_not_found_error(self, output):
        """Check if output indicates command not found"""
        if not output:
            return False
            
        error_patterns = [
            'executable file not found',
            'command not found',
            'not found',
            'no such file or directory'
        ]
        
        output_lower = output.lower()
        return any(pattern in output_lower for pattern in error_patterns)
    
    def get_image_history(self, server_id, environment_id, image_id):
        """
        Get Docker image history (layers) with commands and sizes using Docker API
        
        Args:
            server_id (int): ID of the Portainer server
            environment_id (int): Environment ID
            image_id (str): Docker image ID
            
        Returns:
            list: List of layer objects with commands, sizes, and metadata or None if failed
        """
        server = self.env['j_portainer.server'].browse(server_id)
        if not server:
            _logger.error("Server not found for image history request")
            return None
            
        if not environment_id or not image_id:
            _logger.error("Environment ID and Image ID are required for image history")
            return None

        try:
            # Use Docker Image History API endpoint
            endpoint = f'/api/endpoints/{environment_id}/docker/images/{image_id}/history'
            
            _logger.info(f"Fetching image history for image {image_id} in environment {environment_id}")
            response = server._make_api_request(endpoint, 'GET')
            
            if response.status_code == 200:
                history_data = response.json()
                
                # Process and clean the history data
                processed_layers = []
                for layer in history_data:
                    # Extract layer information
                    layer_info = {
                        'command': layer.get('CreatedBy', '').strip(),
                        'size': layer.get('Size', 0),
                        'created': layer.get('Created', ''),
                        'hash': layer.get('Id', ''),
                        'empty_layer': layer.get('Size', 0) == 0
                    }
                    
                    # Clean up the command for better readability
                    if layer_info['command'].startswith('/bin/sh -c '):
                        layer_info['command'] = layer_info['command'].replace('/bin/sh -c ', 'RUN ')
                    elif layer_info['command'].startswith('COPY '):
                        pass  # Keep COPY commands as-is
                    elif layer_info['command'].startswith('ADD '):
                        pass  # Keep ADD commands as-is
                    elif not layer_info['command']:
                        layer_info['command'] = 'Base layer'
                    
                    processed_layers.append(layer_info)
                
                _logger.info(f"Successfully retrieved {len(processed_layers)} layers for image {image_id}")
                return processed_layers
                
            else:
                _logger.error(f"Failed to get image history: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            _logger.error(f"Error getting image history for {image_id}: {str(e)}")
            return None
    
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
            
        # Endpoint for custom templates has changed for CE 2.27.4 LTS
        # Now using /api/custom_templates/create/file for multipart form data upload
        endpoint = '/api/custom_templates/create/file'
        
        try:
            # Properly set Content-Type header
            headers = {'Content-Type': 'application/json'}
            
            # More robust version detection system
            portainer_version = self._detect_portainer_version(server)
            version_str = portainer_version.get('version_str', '')
            version_major = portainer_version.get('major', 0)
            version_minor = portainer_version.get('minor', 0)
            version_patch = portainer_version.get('patch', 0)
            
            # Log detected version details
            _logger.info(f"Detected Portainer version: {version_str} (Major: {version_major}, Minor: {version_minor}, Patch: {version_patch})")
            
            # If version detection failed, try to detect using endpoints
            if not version_str:
                feature_endpoints = self._check_available_endpoints(server)
                _logger.info(f"Available endpoints detected: {feature_endpoints}")
                
                # Use a hardcoded version if we could detect endpoints
                if feature_endpoints.get('custom_templates'):
                    _logger.info("Using estimated version based on endpoint availability")
                    version_major = 2
                    version_minor = 9  # Assume at least 2.9 if custom templates available
            
            # Prepare API-specific data format
            api_data = dict(template_data)  # Make a copy to avoid modifying the original
            
            # Get auth token to see if we need to handle it specially
            # This is used for version-specific handling if needed
            api_key = server._get_api_key_header()
            
            # Make sure type is an integer for all versions
            if 'type' in api_data and not isinstance(api_data['type'], int):
                try:
                    api_data['type'] = int(api_data['type'])
                except (ValueError, TypeError):
                    api_data['type'] = 1  # Default to container type
            
            # Debug log for payload
            _logger.info(f"Template payload: {api_data}")
            
            # Special case for Portainer CE 2.9+ and 2.10+
            if version_major == 2 and (version_minor >= 9 or version_minor == 0):
                _logger.info("Using Portainer CE 2.9+ format")
                
                # Add/ensure required fields specific to this version
                if 'note' not in api_data:
                    api_data['note'] = False
                
                # Ensure categories is a list
                if 'categories' in api_data and isinstance(api_data['categories'], str):
                    if api_data['categories']:
                        api_data['categories'] = api_data['categories'].split(',')
                    else:
                        api_data['categories'] = ["Custom"]
                elif 'categories' not in api_data:
                    api_data['categories'] = ["Custom"]
                
                # Stack specific fields for 2.9+
                if api_data.get('type') == 2:  # Stack template
                    # Special handling for repository info
                    if 'repository' not in api_data and 'repositoryURL' in api_data:
                        api_data['repository'] = {
                            'url': api_data.get('repositoryURL', ''),
                            'stackfile': api_data.get('composeFilePath', 'docker-compose.yml')
                        }
                        if 'repositoryReferenceName' in api_data:
                            api_data['repository']['reference'] = api_data.get('repositoryReferenceName')
            
            # Special handling for Portainer CE 2.16+
            if version_major == 2 and version_minor >= 16:
                _logger.info("Adding Portainer CE 2.16+ specific fields")
                
                # Add specific fields for 2.16+
                api_data['platform'] = api_data.get('platform', 'linux')
                if 'env' not in api_data:
                    api_data['env'] = []
                    
            # Special handling for Portainer CE 2.27 LTS
            if version_major == 2 and version_minor >= 27:
                _logger.info("Using Portainer CE 2.27 LTS format")
                
                # Make sure all array fields are initialized
                if 'env' not in api_data:
                    api_data['env'] = []
                if 'volumes' not in api_data:
                    api_data['volumes'] = []
                if 'ports' not in api_data:
                    api_data['ports'] = []
            
            # Define all possible endpoints and formats to try
            # For CE 2.27+, we need to use the multipart/form-data format with /api/custom_templates/create/file endpoint
            # Check if we have fileContent for file upload
            has_file_content = False
            file_content = None
            
            # Check for fileContent in api_data or compose_file
            if 'fileContent' in api_data:
                file_content = api_data.get('fileContent')
                has_file_content = bool(file_content)
            elif 'compose_file' in api_data:
                file_content = api_data.get('compose_file')
                has_file_content = bool(file_content)
            elif 'composeFileContent' in api_data:
                file_content = api_data.get('composeFileContent')
                has_file_content = bool(file_content)
                
            # Log if we found file content
            if has_file_content and file_content:
                _logger.info(f"Found file content for multipart form upload, length: {len(file_content)}")
            elif has_file_content:
                _logger.info("Found file content flag but content is None")
            
            # First attempt should be with multipart/form-data and create/file endpoint as it works reliably
            template_creation_attempts = [
                # CE 2.27 LTS Multipart form data approach (most reliable)
                {
                    'endpoint': '/api/custom_templates/create/file',
                    'method': 'POST',
                    'is_multipart': True,
                    'form_data': {
                        'Title': api_data.get('title'),
                        'Description': api_data.get('description', ''),
                        'Note': api_data.get('note', ''),
                        'Platform': str(api_data.get('platform', 1)),  # 1 for Linux, 2 for Windows
                        'Type': str(api_data.get('type', 1)),  # Must be string for form data
                        'Logo': api_data.get('logo', ''),
                        # Add environment ID if available
                        'environmentId': str(api_data.get('environmentId', '')),
                        # Add variables if available as JSON string
                        'Variables': json.dumps(api_data.get('env', [])) if 'env' in api_data else '[]',
                    },
                    'files': {
                        'File': ('template.yml', file_content.encode('utf-8') if file_content else b'version: "3"\nservices:\n  app:\n    image: nginx')
                    },
                    'description': 'CE 2.27 multipart form data with create/file endpoint',
                    'condition': lambda: has_file_content
                },
                # V2 format on primary endpoint
                {
                    'endpoint': '/api/custom_templates',
                    'method': 'POST',
                    'data': api_data,
                    'description': 'V2 format on primary endpoint'
                },
                # Stack templates endpoint (for v2.0+)
                {
                    'endpoint': '/api/stacks/template',
                    'method': 'POST',
                    'data': api_data,
                    'description': 'Stack templates endpoint'
                },
                # Standard endpoint with minimal data
                {
                    'endpoint': '/api/custom_templates',
                    'method': 'POST',
                    'data': {
                        'title': api_data.get('title'),
                        'description': api_data.get('description'),
                        'type': api_data.get('type', 1),
                        'platform': api_data.get('platform', 'linux')
                    },
                    'description': 'Standard endpoint with minimal data (v2)'
                },
                # V2 format on primary endpoint with templates array (fallback)
                {
                    'endpoint': '/api/custom_templates',
                    'method': 'POST',
                    'data': {"version": "2", "templates": [api_data]},
                    'description': 'V2 format with templates array'
                },
                # Stack templates endpoint for stack templates
                {
                    'endpoint': '/api/stacks',
                    'method': 'POST',
                    'data': api_data,
                    'description': 'Stack templates endpoint',
                    'condition': lambda: api_data.get('type') == 2  # Only for stack type
                }
            ]
            
            # Try each endpoint in sequence
            last_error = None
            for attempt in template_creation_attempts:
                # Check if attempt has a condition and skip if not met
                if 'condition' in attempt and not attempt['condition']():
                    continue
                    
                _logger.info(f"Trying template creation with: {attempt['description']}")
                
                try:
                    # Handle multipart form data requests differently
                    if attempt.get('is_multipart'):
                        _logger.info("Using multipart form data request")
                        import requests
                        
                        # Get server URL and API key
                        server_url = server.url
                        if server_url.endswith('/'):
                            server_url = server_url[:-1]
                            
                        api_key = server._get_api_key()
                        
                        # Create complete URL
                        url = f"{server_url}{attempt['endpoint']}"
                        
                        # Create headers with auth
                        req_headers = {'Authorization': f'Bearer {api_key}'}
                        
                        # Log the multipart form data request
                        form_data = attempt.get('form_data', {})
                        files = attempt.get('files', {})
                        
                        _logger.info(f"Sending multipart form data to {url}")
                        _logger.info(f"Form data: {form_data}")
                        _logger.info(f"Files: {list(files.keys())}")
                        
                        # Send the multipart request
                        response = requests.post(
                            url=url,
                            headers=req_headers,
                            data=form_data,
                            files=files,
                            verify=server.verify_ssl
                        )
                    else:
                        # Use standard API request
                        response = server._make_api_request(
                            attempt['endpoint'], 
                            attempt['method'], 
                            data=attempt['data'], 
                            headers=headers
                        )
                    
                    if response.status_code in [200, 201, 202, 204]:
                        try:
                            # Try to parse response
                            result = response.json()
                            _logger.info(f"Template created successfully with {attempt['description']}. Response: {result}")
                            return result
                        except Exception as e:
                            # Empty response is still success for some endpoints
                            _logger.info(f"Empty or non-JSON response from {attempt['description']} (still success)")
                            # For empty responses, return minimal success data
                            return {'Id': 0, 'success': True, 'method': attempt['description']}
                    else:
                        _logger.warning(f"Failed with {attempt['description']}: {response.status_code} - {response.text}")
                        last_error = {
                            'status_code': response.status_code,
                            'text': response.text,
                            'method': attempt['description']
                        }
                except Exception as e:
                    _logger.warning(f"Exception with {attempt['description']}: {str(e)}")
                    last_error = {
                        'error': str(e),
                        'method': attempt['description']
                    }
            
            # If we get here, all attempts failed
            _logger.error(f"All template creation attempts failed. Last error: {last_error}")
            
            # Check if the feature is available at all
            _logger.info("Checking if custom templates feature is available")
            feature_endpoints = self._check_available_endpoints(server)
            if not feature_endpoints.get('custom_templates'):
                _logger.error("Custom templates feature not available in this Portainer version")
                    
            return None
        except Exception as e:
            _logger.error(f"Exception during template creation: {str(e)}")
            return None
            
    def update_template(self, server_id, template_id, template_data, environment_id=None):
        """Update a custom template in Portainer
        
        Args:
            server_id (int): ID of the Portainer server
            template_id (int): ID of the template to update
            template_data (dict): Updated template data
            
        Returns:
            dict: Response data or None if failed
        """
        server = self.env['j_portainer.server'].browse(server_id)
        if not server:
            return {'error': 'Server not found'}
            
        # Normalize type field - ensure it's an integer
        if 'type' in template_data and isinstance(template_data['type'], str):
            try:
                template_data['type'] = int(template_data['type'])
            except ValueError:
                template_data['type'] = 1  # Default to container type
        
        # Log the template data for debugging
                    
        # Use the API endpoint for custom templates (PUT doesn't need environment parameter)
        endpoint = f'/api/custom_templates/{template_id}'
        
        try:
            # Properly set Content-Type header
            headers = {'Content-Type': 'application/json'}
            
            # Use our enhanced version detection
            portainer_version = self._detect_portainer_version(server)
            version_str = portainer_version.get('version_str', '')
            version_major = portainer_version.get('major', 0)
            version_minor = portainer_version.get('minor', 0)
            
            # Log detected version details
            _logger.info(f"Detected Portainer version for update: {version_str} (Major: {version_major}, Minor: {version_minor})")
            
            # Prepare API-specific data format
            api_data = dict(template_data)  # Make a copy to avoid modifying the original
            
            # Make sure type is an integer for all versions
            if 'type' in api_data and not isinstance(api_data['type'], int):
                try:
                    api_data['type'] = int(api_data['type'])
                except (ValueError, TypeError):
                    api_data['type'] = 1  # Default to container type
                    
            # Make sure platform is an integer for CE 2.27+
            if 'platform' in api_data and isinstance(api_data['platform'], str):
                try:
                    # Map platform strings to integers for Portainer v2 API
                    platform_map = {
                        'linux': 1,
                        'windows': 2
                    }
                    api_data['platform'] = platform_map.get(api_data['platform'].lower(), 1)  # Default to Linux (1)
                    _logger.info(f"Converted platform string to integer: {api_data['platform']}")
                except Exception as e:
                    _logger.warning(f"Error converting platform to integer: {str(e)}")
                    api_data['platform'] = 1  # Default to Linux (1)
            
            # Special case for Portainer CE 2.9+ and 2.10+
            if version_major == 2 and (version_minor >= 9 or version_minor == 0):
                _logger.info("Using Portainer CE 2.9+ format for update")
                
                # Add/ensure required fields specific to this version
                if 'note' not in api_data:
                    api_data['note'] = False
                
                # Ensure categories is a list
                if 'categories' in api_data and isinstance(api_data['categories'], str):
                    if api_data['categories']:
                        api_data['categories'] = api_data['categories'].split(',')
                    else:
                        api_data['categories'] = ["Custom"]
                elif 'categories' not in api_data:
                    api_data['categories'] = ["Custom"]
                
                # Stack specific fields for 2.9+
                if api_data.get('type') == 2:  # Stack template
                    # Special handling for repository info
                    if 'repository' not in api_data and 'repositoryURL' in api_data:
                        api_data['repository'] = {
                            'url': api_data.get('repositoryURL', ''),
                            'stackfile': api_data.get('composeFilePath', 'docker-compose.yml')
                        }
                        if 'repositoryReferenceName' in api_data:
                            api_data['repository']['reference'] = api_data.get('repositoryReferenceName')
            
            # Special handling for Portainer CE 2.16+
            if version_major == 2 and version_minor >= 16:
                _logger.info("Adding Portainer CE 2.16+ specific fields for update")
                
                # Add specific fields for 2.16+
                if 'platform' not in api_data:
                    api_data['platform'] = 1  # Default to Linux (1)
                if 'env' not in api_data:
                    api_data['env'] = []
                    
            # Special handling for Portainer CE 2.27 LTS
            if version_major == 2 and version_minor >= 27:
                _logger.info("Using Portainer CE 2.27 LTS format for update")
                
                # Make sure all array fields are initialized
                if 'env' not in api_data:
                    api_data['env'] = []
                if 'volumes' not in api_data:
                    api_data['volumes'] = []
                if 'ports' not in api_data:
                    api_data['ports'] = []
            
            # Make the update request
            response = server._make_api_request(endpoint, 'PUT', data=api_data, headers=headers, environment_id=environment_id)
            
            if response.status_code in [200, 201, 204]:
                try:
                    result = response.json()
                    _logger.info(f"Template updated successfully: {result}")
                    return result
                except Exception as e:
                    _logger.warning(f"Error parsing update response: {str(e)}")
                    if response.text:
                        _logger.info(f"Raw update response: {response.text}")
                    return {'Id': template_id}  # Assume success with empty response
            else:
                error_message = f"{response.status_code} - {response.text}"
                _logger.error(f"Error updating template: {error_message}")
                return {
                    'error': error_message,
                    'status_code': response.status_code,
                    'text': response.text
                }
                
        except Exception as e:
            _logger.error(f"Exception during template update: {str(e)}")
            return {'error': str(e)}
            
    def _detect_portainer_version(self, server):
        """Detect Portainer version with detailed parsing
        
        Args:
            server (j_portainer.server): Portainer server record
            
        Returns:
            dict: Version information with keys:
                - version_str: Raw version string
                - major: Major version number
                - minor: Minor version number
                - patch: Patch version number
                - error: Error message if any
        """
        result = {
            'version_str': '',
            'major': 0,
            'minor': 0,
            'patch': 0,
            'error': None
        }
        
        try:
            # Try /api/system/version endpoint first (newer Portainer versions)
            version_response = server._make_api_request('/api/system/version', 'GET')
            
            if version_response.status_code == 200:
                try:
                    version_info = version_response.json()
                    version_str = version_info.get('Version', '')
                    result['version_str'] = version_str
                    
                    # Parse version string (format: 2.x.x)
                    if version_str:
                        version_parts = version_str.split('.')
                        if len(version_parts) >= 3:
                            try:
                                result['major'] = int(version_parts[0])
                                result['minor'] = int(version_parts[1])
                                result['patch'] = int(version_parts[2])
                            except (ValueError, IndexError) as e:
                                result['error'] = f"Error parsing version parts: {str(e)}"
                        else:
                            result['error'] = f"Invalid version format: {version_str}"
                except Exception as e:
                    result['error'] = f"Error parsing version info: {str(e)}"
            elif version_response.status_code == 404:
                # Try alternative version endpoint for older Portainer
                alt_version_response = server._make_api_request('/api/status', 'GET')
                if alt_version_response.status_code == 200:
                    try:
                        alt_version_info = alt_version_response.json()
                        version_str = alt_version_info.get('Version', '')
                        result['version_str'] = version_str
                        
                        # Parse version string
                        if version_str:
                            version_parts = version_str.split('.')
                            if len(version_parts) >= 3:
                                try:
                                    result['major'] = int(version_parts[0])
                                    result['minor'] = int(version_parts[1])
                                    result['patch'] = int(version_parts[2])
                                except (ValueError, IndexError) as e:
                                    result['error'] = f"Error parsing version parts: {str(e)}"
                            else:
                                result['error'] = f"Invalid version format: {version_str}"
                    except Exception as e:
                        result['error'] = f"Error parsing alternative version info: {str(e)}"
                else:
                    result['error'] = "Could not detect Portainer version"
            else:
                result['error'] = f"Error fetching version: {version_response.status_code} - {version_response.text}"
                
        except Exception as e:
            result['error'] = f"Exception during version detection: {str(e)}"
            
        return result
        
    def import_template_file(self, server_id, template_data):
        """Import a template from a file
        
        This is an alternative method when the API creation fails.
        Uses the v2 API endpoints only.
        
        Args:
            server_id (int): ID of the Portainer server
            template_data (dict): Template data in format compatible with file import
            
        Returns:
            dict: Created template data or None if failed
        """
        server = self.env['j_portainer.server'].browse(server_id)
        if not server:
            return None
            
        try:
            # Convert template data to JSON string
            template_json = json.dumps(template_data, indent=2)
            _logger.info(f"Importing template via V2 API: {template_json}")
            
            # Try V2 API endpoints only
            v2_endpoints = [
                '/api/custom_templates/file',
                '/api/custom_templates',
                '/api/custom_templates/create'
            ]
            
            headers = {'Content-Type': 'application/json'}
            
            # Try POST method first
            for endpoint in v2_endpoints:
                try:
                    _logger.info(f"Trying POST to {endpoint}")
                    response = server._make_api_request(endpoint, 'POST', data=template_data, headers=headers)
                    if response.status_code in [200, 201, 202, 204]:
                        try:
                            result = response.json()
                            _logger.info(f"Template imported successfully via POST to {endpoint}. Response: {result}")
                            return result
                        except Exception as e:
                            # Empty response is still success for some endpoints
                            _logger.info(f"Empty or non-JSON response from {endpoint} (still success)")
                            return {'success': True, 'method': f'post_{endpoint}'}
                    else:
                        _logger.warning(f"Failed with POST to {endpoint}: {response.status_code} - {response.text}")
                except Exception as e:
                    _logger.warning(f"Error with POST to {endpoint}: {str(e)}")
            
            # Try PUT method next
            for endpoint in v2_endpoints:
                try:
                    _logger.info(f"Trying PUT to {endpoint}")
                    response = server._make_api_request(endpoint, 'PUT', data=template_data, headers=headers)
                    if response.status_code in [200, 201, 202, 204]:
                        try:
                            result = response.json()
                            _logger.info(f"Template imported successfully via PUT to {endpoint}. Response: {result}")
                            return result
                        except Exception as e:
                            # Empty response is still success for some endpoints
                            _logger.info(f"Empty or non-JSON response from PUT to {endpoint} (still success)")
                            return {'success': True, 'method': f'put_{endpoint}'}
                    else:
                        _logger.warning(f"Failed with PUT to {endpoint}: {response.status_code} - {response.text}")
                except Exception as e:
                    _logger.warning(f"Error with PUT to {endpoint}: {str(e)}")
            
            # If all attempts fail, return None
            _logger.error("All V2 API template import attempts failed")
            return None
            
        except Exception as e:
            _logger.error(f"Exception during template import: {str(e)}")
            return None
            
    def direct_api_call(self, server_id, endpoint, method='GET', data=None, params=None, headers=None, use_multipart=False):
        """Make a direct API call to Portainer
        
        This is a utility method for making direct API calls to Portainer without
        the standard endpoint prefixes. Useful for custom templates and file uploads.
        
        Args:
            server_id (int): ID of the Portainer server
            endpoint (str): API endpoint to call (e.g., "/api/custom_templates")
            method (str): HTTP method to use (GET, POST, PUT, DELETE)
            data (dict, optional): Data to send in the request body
            params (dict, optional): Query parameters for the request
            headers (dict, optional): Additional headers to include
            use_multipart (bool): Whether to use multipart form encoding
            
        Returns:
            response object: The raw response from the server or dict with result
        """
        server = self.env['j_portainer.server'].browse(server_id)
        if not server:
            _logger.error(f"Server with ID {server_id} not found")
            return None
            
        try:
            # Ensure endpoint starts with /
            if not endpoint.startswith('/'):
                endpoint = f'/{endpoint}'
                
            # Ensure endpoint has /api prefix if not already specified
            if not endpoint.startswith('/api'):
                endpoint = f'/api{endpoint}'
                
            # Make the API call
            _logger.info(f"Making direct API call to {endpoint} with method {method}")
            response = server._make_api_request(endpoint, method, data=data, params=params, headers=headers, use_multipart=use_multipart)
            
            # Log the response status
            _logger.info(f"Direct API call response status: {response.status_code}")
            
            # For successful responses, parse JSON if possible
            if response.status_code in [200, 201, 202, 204]:
                try:
                    # Try to parse JSON response
                    result = response.json()
                    _logger.info(f"Successfully parsed JSON response from {endpoint}")
                    return result
                except Exception as e:
                    # If not JSON or empty response, return a success dict
                    _logger.info(f"Non-JSON response from {endpoint}, returning success dict")
                    if response.text and len(response.text.strip()) > 0:
                        return {'success': True, 'response_text': response.text[:100] + '...'}
                    else:
                        return {'success': True, 'message': f'Successful {method} request to {endpoint}'}
            else:
                # Return the response object for error handling
                return response
        except Exception as e:
            _logger.error(f"Error making direct API call to {endpoint}: {str(e)}")
            return {'error': str(e), 'success': False}
            
    def _check_available_endpoints(self, server):
        """Check which endpoints are available in the Portainer instance
        
        Args:
            server (j_portainer.server): Portainer server record
            
        Returns:
            dict: Map of feature names to boolean availability
        """
        features = {
            'custom_templates': False,
            'stacks': False,
            'containers': False,
            'images': False,
            'volumes': False,
            'networks': False,
            'templates': False,
        }
        
        # Test endpoints to determine available features
        endpoints_to_check = {
            'custom_templates': '/api/custom_templates',
            'stacks': '/api/stacks',
            'containers': '/api/endpoints/1/docker/containers/json',
            'images': '/api/endpoints/1/docker/images/json',
            'volumes': '/api/endpoints/1/docker/volumes',
            'networks': '/api/endpoints/1/docker/networks',
            'templates': '/api/templates',
        }
        
        for feature, endpoint in endpoints_to_check.items():
            try:
                response = server._make_api_request(endpoint, 'GET')
                # Consider 200, 204, 401, 403 as endpoint exists but might need auth
                if response.status_code in [200, 204, 401, 403]:
                    features[feature] = True
                # 404 means endpoint doesn't exist
                elif response.status_code == 404:
                    features[feature] = False
                else:
                    # For other status codes, assume endpoint might exist but has other issues
                    # Use False instead of None to avoid type issues
                    features[feature] = False
            except Exception as e:
                _logger.warning(f"Error checking endpoint {endpoint}: {str(e)}")
                features[feature] = False  # Use False instead of None to avoid type issues
                
        return features
        
    def connect_container_to_network(self, server_id, environment_id, network_id, container_id, config=None):
        """Connect container to a network
        
        Args:
            server_id (int): Portainer server ID
            environment_id (int): Environment ID
            network_id (str): Network ID
            container_id (str): Container ID
            config (dict, optional): Network connection configuration (IPv4Address, Aliases, etc.)
            
        Returns:
            bool: Operation success
        """
        server = self.env['j_portainer.server'].browse(server_id)
        
        if config is None:
            config = {}
            
        data = {
            "Container": container_id,
            "EndpointID": str(environment_id),
            "NetworkID": network_id,
            "Config": config
        }
        
        endpoint = f'/api/endpoints/{environment_id}/docker/networks/{network_id}/connect'
        response = server._make_api_request(endpoint, method='POST', data=data, environment_id=environment_id)
        
        return response.status_code in (200, 204)
        
    def disconnect_container_from_network(self, server_id, environment_id, network_id, container_id, force=False):
        """Disconnect container from a network
        
        Args:
            server_id (int): Portainer server ID
            environment_id (int): Environment ID
            network_id (str): Network ID
            container_id (str): Container ID
            force (bool, optional): Force disconnect
            
        Returns:
            bool: Operation success
        """
        server = self.env['j_portainer.server'].browse(server_id)
        
        data = {
            "Container": container_id,
            "EndpointID": str(environment_id),
            "NetworkID": network_id,
            "Force": force
        }
        
        endpoint = f'/api/endpoints/{environment_id}/docker/networks/{network_id}/disconnect'
        response = server._make_api_request(endpoint, method='POST', data=data, environment_id=environment_id)
        
        return response.status_code in (200, 204)
        
    def update_container_labels(self, server_id, environment_id, container_id, labels):
        """Update container labels in Portainer
        
        Args:
            server_id (int): Portainer server ID
            environment_id (int): Environment ID
            container_id (str): Container ID
            labels (dict): Container labels to set
            
        Returns:
            dict: Result with success status and message
        """
        import logging
        import time
        _logger = logging.getLogger(__name__)
        
        result = {
            'success': False,
            'message': ''
        }
        
        server = self.env['j_portainer.server'].browse(server_id)
        
        # Get detailed container information
        _logger.info(f"Getting container info for container {container_id}")
        endpoint = f'/api/endpoints/{environment_id}/docker/containers/{container_id}/json'
        response = server._make_api_request(endpoint, method='GET', environment_id=environment_id)
        
        if response.status_code != 200:
            result['message'] = f"Failed to get container info: {response.status_code} - {response.text}"
            _logger.error(result['message'])
            return result
            
        container_info = response.json()
        
        # Container must be recreated to update labels
        # Strategy 1: Use Docker update API - may not work for labels on all versions
        try:
            _logger.info(f"Updating container {container_id} labels via update API")
            endpoint = f'/api/endpoints/{environment_id}/docker/containers/{container_id}/update'
            
            # Create container update configuration
            config = {
                "Labels": labels
            }
            
            # Try updating using API
            update_response = server._make_api_request(endpoint, method='POST', data=config, environment_id=environment_id)
            
            if update_response.status_code == 200:
                _logger.info(f"Successfully updated container {container_id} labels via update API")
                result['success'] = True
                result['message'] = "Labels updated successfully"
                return result
            
            # Log debug info
            _logger.warning(f"Container update API failed: {update_response.status_code} - {update_response.text}")
        except Exception as e:
            _logger.warning(f"Error using update API: {str(e)}")
        
        # If we get here, the first approach failed, try the commit/recreate approach
        # Strategy 2: Commit container changes, then recreate with same config but new labels
        try:
            _logger.info(f"Trying to update container {container_id} labels via commit/recreate")
            
            # Check if container is running
            is_running = container_info.get('State', {}).get('Running', False)
            
            # Extract container configuration
            config = container_info.get('Config', {})
            host_config = container_info.get('HostConfig', {})
            network_settings = container_info.get('NetworkSettings', {})
            
            # Apply new labels - this is the change we want
            config['Labels'] = labels
            
            # Step 1: If running, stop the container
            if is_running:
                _logger.info(f"Stopping container {container_id}")
                stop_endpoint = f'/api/endpoints/{environment_id}/docker/containers/{container_id}/stop'
                stop_response = server._make_api_request(stop_endpoint, method='POST', environment_id=environment_id)
                if stop_response.status_code not in [204, 304]:
                    result['message'] = f"Failed to stop container: {stop_response.status_code} - {stop_response.text}"
                    _logger.error(result['message'])
                    return result
            
            # Step 2: Rename the old container with a temporary name
            _logger.info(f"Renaming container {container_id}")
            old_name = container_info.get('Name', '').lstrip('/')
            new_name = f"{old_name}_old_{int(time.time())}"
            rename_endpoint = f'/api/endpoints/{environment_id}/docker/containers/{container_id}/rename'
            rename_params = {'name': new_name}
            rename_response = server._make_api_request(rename_endpoint, method='POST', params=rename_params, environment_id=environment_id)
            if rename_response.status_code != 204:
                # Restart container if it was running
                if is_running:
                    _logger.info(f"Restarting container {container_id}")
                    start_endpoint = f'/api/endpoints/{environment_id}/docker/containers/{container_id}/start'
                    server._make_api_request(start_endpoint, method='POST', environment_id=environment_id)
                result['message'] = f"Failed to rename container: {rename_response.status_code} - {rename_response.text}"
                _logger.error(result['message'])
                return result
            
            # Step 3: Create a new container with the same configuration but new labels
            _logger.info(f"Creating new container with updated labels")
            create_endpoint = f'/api/endpoints/{environment_id}/docker/containers/create'
            create_params = {'name': old_name}
            
            # Prepare create configuration
            create_config = {
                'Image': config.get('Image'),
                'Entrypoint': config.get('Entrypoint'),
                'Cmd': config.get('Cmd'),
                'Env': config.get('Env'),
                'Labels': labels,  # New labels
                'ExposedPorts': config.get('ExposedPorts'),
                'HostConfig': host_config,
                'NetworkingConfig': {
                    'EndpointsConfig': network_settings.get('Networks', {})
                }
            }
            
            create_response = server._make_api_request(create_endpoint, method='POST', params=create_params, 
                                                     data=create_config, environment_id=environment_id)
            
            if create_response.status_code != 201:
                # Rename back the old container
                rename_back_endpoint = f'/api/endpoints/{environment_id}/docker/containers/{container_id}/rename'
                rename_back_params = {'name': old_name}
                server._make_api_request(rename_back_endpoint, method='POST', params=rename_back_params, 
                                      environment_id=environment_id)
                # Restart if it was running
                if is_running:
                    start_endpoint = f'/api/endpoints/{environment_id}/docker/containers/{container_id}/start'
                    server._make_api_request(start_endpoint, method='POST', environment_id=environment_id)
                
                result['message'] = f"Failed to create new container: {create_response.status_code} - {create_response.text}"
                _logger.error(result['message'])
                return result
            
            # Step 4: Get the new container ID
            new_container = create_response.json()
            new_container_id = new_container.get('Id')
            
            # Step 5: Start the new container if the old one was running
            if is_running:
                _logger.info(f"Starting new container {new_container_id}")
                start_endpoint = f'/api/endpoints/{environment_id}/docker/containers/{new_container_id}/start'
                start_response = server._make_api_request(start_endpoint, method='POST', environment_id=environment_id)
                if start_response.status_code != 204:
                    result['message'] = f"Failed to start new container: {start_response.status_code} - {start_response.text}"
                    _logger.error(result['message'])
                    return result
            
            # Step 6: Remove the old container
            _logger.info(f"Removing old container {container_id}")
            remove_endpoint = f'/api/endpoints/{environment_id}/docker/containers/{container_id}'
            remove_params = {'force': True}
            remove_response = server._make_api_request(remove_endpoint, method='DELETE', params=remove_params, 
                                                     environment_id=environment_id)
            
            if remove_response.status_code != 204:
                _logger.warning(f"Failed to remove old container: {remove_response.status_code} - {remove_response.text}")
                # We don't return error here, as the new container is already running
            
            # Success! Labels have been updated
            result['success'] = True
            result['message'] = "Labels updated successfully via container recreation"
            _logger.info(f"Successfully updated container labels via commit/recreate")
            return result
            
        except Exception as e:
            _logger.error(f"Error in commit/recreate approach: {str(e)}")
            result['message'] = f"Error updating labels: {str(e)}"
            return result
            
        # If we get here, both approaches failed
        result['message'] = "Failed to update container labels using multiple approaches"
        _logger.error(result['message'])
        return result