#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models
import logging
import json
import io
import uuid
import urllib.request
import urllib.parse
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
    
    def stack_action(self, server_id, stack_id, action, data=None):
        """Perform action on a stack
        
        Args:
            server_id (int): ID of the Portainer server
            stack_id (int): Stack ID
            action (str): Action to perform (delete, stop, start, redeploy, etc.)
            data (dict, optional): Additional data for the action
            
        Returns:
            bool or dict: True if successful with no response, or dict with response data
        """
        server = self.env['j_portainer.server'].browse(server_id)
        if not server:
            return {'error': 'Server not found'}
            
        if action == 'delete':
            endpoint = f'/api/stacks/{stack_id}'
            response = server._make_api_request(endpoint, 'DELETE')
            if response.status_code in [200, 201, 204]:
                return True
            return {'error': f'Failed to delete stack: {response.text}'}
            
        elif action in ['start', 'stop']:
            endpoint = f'/api/stacks/{stack_id}/' + ('start' if action == 'start' else 'stop')
            response = server._make_api_request(endpoint, 'POST')
            if response.status_code in [200, 201, 204]:
                return True
            return {'error': f'Failed to {action} stack: {response.text}'}
            
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
            # Custom template deployment (using v2 endpoint)
            endpoint = f'/api/custom_templates/{template_id}'
            method = 'POST'
        else:
            # Standard template deployment (using v2 endpoint)
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
            template_creation_attempts = [
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
                # Removed all v1 endpoints per request - only using v2 endpoints
                # V2 format on primary endpoint
                {
                    'endpoint': '/api/custom_templates',
                    'method': 'POST',
                    'data': {"version": "2", "templates": [api_data]},
                    'description': 'V2 format on primary endpoint'
                },
                # Stack templates endpoint for stack templates
                {
                    'endpoint': '/api/stacks',
                    'method': 'POST',
                    'data': api_data,
                    'description': 'Stack templates endpoint',
                    'condition': lambda: api_data.get('type') == 2  # Only for stack type
                },
                # Template with no version or type
                {
                    'endpoint': '/api/custom_templates',
                    'method': 'POST',
                    'data': {k: v for k, v in api_data.items() if k not in ['version', 'type']},
                    'description': 'Standard endpoint with minimal data'
                },
                # PUT method for older versions
                {
                    'endpoint': '/api/custom_templates',
                    'method': 'PUT',
                    'data': api_data,
                    'description': 'Standard endpoint with PUT method'
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
            
    def update_template(self, server_id, template_id, template_data):
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
        _logger.info(f"Updating template {template_id} with data: {json.dumps(template_data, indent=2)}")
            
        # Use the API endpoint for custom templates
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
                api_data['platform'] = api_data.get('platform', 'linux')
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
            response = server._make_api_request(endpoint, 'PUT', data=api_data, headers=headers)
            
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
                _logger.error(f"Error updating template: {response.status_code} - {response.text}")
                return {'error': f"API error: {response.status_code} - {response.text}"}
                
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