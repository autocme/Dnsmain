import json
import logging
import base64
import threading
import time
import uuid
import os
import tempfile
from datetime import datetime, timedelta
from werkzeug.exceptions import NotFound

from odoo import http
from odoo.http import request, Response
from odoo.exceptions import AccessError, UserError

# Try to import geventwebsocket
try:
    from geventwebsocket import WebSocketError
    from geventwebsocket.handler import WebSocketHandler
    _HAS_WEBSOCKET = True
except ImportError:
    _HAS_WEBSOCKET = False
    _logger = logging.getLogger(__name__)
    _logger.warning("WebSocket support is not available. Please install gevent-websocket.")

_logger = logging.getLogger(__name__)

# WebSocket sessions storage
WEBSOCKET_SESSIONS = {}
LOCKS = {}

class WebSSHController(http.Controller):
    """Controller for WebSSH integration"""
    
    @http.route('/webssh/auth', type='json', auth='user')
    def webssh_auth(self, client_id=None):
        """Authenticate and get connection details for WebSSH"""
        if not client_id:
            return {'error': 'No client ID provided'}
        
        try:
            # Get the SSH client record
            ssh_client = request.env['ssh.client'].browse(int(client_id))
            if not ssh_client.exists():
                return {'error': 'SSH client not found'}
            
            # Check access rights
            if not request.env.user.has_group('base.group_user'):
                return {'error': 'Access denied'}
            
            # Get WebSSH connection details
            connection_info = ssh_client.get_webssh_connection()
            
            return {
                'success': True,
                'url': connection_info.get('url'),
                'port': connection_info.get('port')
            }
            
        except Exception as e:
            _logger.error(f"WebSSH authentication error: {e}")
            return {'error': str(e)}
    
    @http.route('/webssh/token/<string:token>', type='http', auth='user')
    def webssh_token_validation(self, token):
        """Validate WebSSH token and return connection details"""
        try:
            # Decode the token
            token_data = json.loads(base64.urlsafe_b64decode(token.encode()).decode())
            
            # Check token expiration (10 minutes)
            token_time = datetime.fromisoformat(token_data.get('timestamp'))
            if datetime.now() - token_time > timedelta(minutes=10):
                return Response("Token expired", status=401)
            
            # Get the SSH client
            client_id = token_data.get('id')
            ssh_client = request.env['ssh.client'].browse(int(client_id))
            
            if not ssh_client.exists():
                return Response("Invalid SSH client", status=404)
            
            # Check access rights
            if not request.env.user.has_group('base.group_user'):
                return Response("Access denied", status=403)
            
            # Handle private key if using key authentication
            key_path = None
            if ssh_client.auth_method == 'key' and ssh_client.private_key:
                key_path = ssh_client.create_temp_key_file()
                token_data['key_filename'] = key_path
            
            # Return connection details as JSON
            resp = Response(json.dumps(token_data), content_type='application/json')
            
            # Register a cleanup function to remove temporary key file
            if key_path:
                @resp.call_on_close
                def cleanup():
                    try:
                        os.unlink(key_path)
                    except Exception as e:
                        _logger.error(f"Failed to clean up temporary key file: {e}")
            
            return resp
            
        except Exception as e:
            _logger.error(f"WebSSH token validation error: {e}")
            return Response(f"Error: {str(e)}", status=500)
    
    @http.route('/webssh/', type='http', auth='user')
    def webssh_client(self, **kw):
        """Render the WebSSH client interface with a simple command form"""
        client_id = kw.get('client_id')
        command = kw.get('command')
        history = kw.get('history', '')  # Command history
        
        if not client_id:
            return request.render('nalios_ssh_clients.webssh_error', {
                'error': 'No SSH client specified'
            })
        
        try:
            # Get the SSH client
            ssh_client = request.env['ssh.client'].browse(int(client_id))
            if not ssh_client.exists():
                return request.render('nalios_ssh_clients.webssh_error', {
                    'error': 'SSH client not found'
                })
            
            # Execute command if provided and append to history
            output = None
            command_history = []
            
            if history:
                # Parse the history from the hidden field
                try:
                    command_history = json.loads(history)
                except:
                    command_history = []
            
            if command:
                # Execute the command
                output = ssh_client.exec_command(command)
                
                # Add command to history (max 20 commands)
                if command not in command_history:
                    command_history.insert(0, command)
                    if len(command_history) > 20:
                        command_history.pop()
            
            # Check if connection is working with a simple test command
            is_connected = True
            if not command:
                try:
                    test_output = ssh_client.test_connection()
                    if not test_output or 'error' in test_output.lower():
                        is_connected = False
                except:
                    is_connected = False
            
            # Render the template with the SSH information and command output
            return request.render('nalios_ssh_clients.webssh_client', {
                'ssh_client': ssh_client,
                'client_id': client_id,
                'command_output': output,
                'command': command,
                'command_history': command_history,
                'command_history_json': json.dumps(command_history),
                'is_connected': is_connected
            })
            
        except Exception as e:
            _logger.error(f"WebSSH client render error: {e}")
            return request.render('nalios_ssh_clients.webssh_error', {
                'error': str(e)
            })
    
    @http.route('/webssh/execute', type='json', auth='user')
    def webssh_execute(self, client_id=None, command=None, **kw):
        """Execute a command on the SSH client directly
        
        This is a simpler alternative to WebSockets for command execution
        """
        if not client_id or not command:
            return {'error': 'Missing client_id or command'}
        
        try:
            # Get the SSH client
            ssh_client = request.env['ssh.client'].browse(int(client_id))
            if not ssh_client.exists():
                return {'error': 'SSH client not found'}
            
            # Execute the command
            result = ssh_client.exec_command(command)
            
            # Return the result
            return {
                'success': True,
                'result': result
            }
            
        except Exception as e:
            _logger.error(f"WebSSH command execution error: {e}")
            return {'error': str(e)}
            
    @http.route('/webssh/socket/<string:session_id>', type='http', auth='user')
    def webssh_socket(self, session_id, **kw):
        """WebSocket endpoint for SSH terminal interactions"""
        if not _HAS_WEBSOCKET:
            return Response("WebSocket support is not available", status=501)
            
        wsock = request.httprequest.environ.get('wsgi.websocket')
        if not wsock:
            return Response("Expected WebSocket request", status=400)
            
        try:
            # Get session data from the session ID
            if session_id not in WEBSOCKET_SESSIONS:
                wsock.send(json.dumps({'error': 'Invalid session ID'}))
                wsock.close()
                return Response("Invalid session ID", status=404)
            
            # Get session data
            session_data = WEBSOCKET_SESSIONS.get(session_id)
            client_id = session_data.get('client_id')
            
            # Create a lock for this session if it doesn't exist
            if session_id not in LOCKS:
                LOCKS[session_id] = threading.Lock()
            
            # Get SSH client connection
            ssh_client = request.env['ssh.client'].browse(int(client_id))
            if not ssh_client.exists():
                wsock.send(json.dumps({'error': 'SSH client not found'}))
                wsock.close()
                return Response("SSH client not found", status=404)
            
            # Send initial connection success message
            wsock.send(json.dumps({
                'status': 'connected',
                'message': f'Connected to {ssh_client.hostname}'
            }))
            
            # Main WebSocket loop
            while True:
                try:
                    # Wait for message from client
                    message = wsock.receive()
                    if message is None:
                        break  # Client closed connection
                    
                    # Parse message
                    data = json.loads(message)
                    msg_type = data.get('type')
                    
                    if msg_type == 'ping':
                        # Respond to ping with pong
                        wsock.send(json.dumps({'type': 'pong'}))
                        
                    elif msg_type == 'command':
                        # Execute command
                        command = data.get('data', '')
                        
                        # Execute command with lock to prevent concurrent execution
                        with LOCKS[session_id]:
                            output = ssh_client.exec_command(command)
                            
                        # Send command output back to client
                        wsock.send(json.dumps({
                            'type': 'output',
                            'data': output
                        }))
                        
                    elif msg_type == 'disconnect':
                        # Client is disconnecting - break the loop
                        _logger.info(f"Client requested disconnect for session {session_id}")
                        
                        # Send acknowledgment back
                        wsock.send(json.dumps({
                            'type': 'info',
                            'message': 'Disconnected from server'
                        }))
                        
                        # Break out of the loop to close the connection
                        break
                    
                except WebSocketError:
                    break  # Socket closed or errored
                except Exception as e:
                    _logger.error(f"WebSocket error: {e}")
                    wsock.send(json.dumps({
                        'type': 'error',
                        'error': str(e)
                    }))
                    break
            
            # Clean up
            try:
                # Clean up the SSH connection by calling disconnect
                if ssh_client and session_id in WEBSOCKET_SESSIONS:
                    ssh_client.disconnect_client()
                    _logger.info(f"SSH client {client_id} disconnected")
            except Exception as e:
                _logger.error(f"Error disconnecting SSH client: {e}")
                
            # Remove session data
            if session_id in LOCKS:
                del LOCKS[session_id]
            if session_id in WEBSOCKET_SESSIONS:
                del WEBSOCKET_SESSIONS[session_id]
                
            return Response("WebSocket closed", status=200)
            
        except Exception as e:
            _logger.error(f"WebSocket handler error: {e}")
            return Response(f"WebSocket error: {str(e)}", status=500)
    
    @http.route('/webssh/ws_initialize', type='json', auth='user')
    def webssh_initialize(self, client_id=None):
        """Initialize a WebSocket session and return session ID"""
        if not client_id:
            return {'error': 'No client ID provided'}
        
        try:
            # Validate the client exists
            ssh_client = request.env['ssh.client'].browse(int(client_id))
            if not ssh_client.exists():
                return {'error': 'SSH client not found'}
                
            # Generate a unique session ID
            session_id = str(uuid.uuid4())
            
            # Store session data
            WEBSOCKET_SESSIONS[session_id] = {
                'client_id': client_id,
                'user_id': request.env.user.id,
                'created_at': datetime.now().isoformat()
            }
            
            # Return session ID to the client
            return {
                'success': True,
                'session_id': session_id
            }
            
        except Exception as e:
            _logger.error(f"WebSocket initialization error: {e}")
            return {'error': str(e)}