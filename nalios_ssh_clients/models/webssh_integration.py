import json
import os
import logging
import threading
import tempfile
import base64
from datetime import datetime

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

# Import the webssh components
from webssh.handler import IndexHandler, WsockHandler
from webssh.settings import get_app_settings
import tornado.web
import tornado.ioloop
import tornado.escape

_logger = logging.getLogger(__name__)

class WebSSHServer:
    """Singleton class to manage the WebSSH server instance"""
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(WebSSHServer, cls).__new__(cls)
                cls._instance.initialized = False
                cls._instance.server = None
                cls._instance.ioloop = None
                cls._instance.thread = None
                cls._instance.port = None
                cls._instance.handlers = []
                cls._instance.clients = {}
            return cls._instance
    
    def initialize(self, port=8888):
        """Initialize the WebSSH server"""
        if self.initialized:
            return self.port
        
        self.port = port
        settings = get_app_settings(self.port)
        
        # Create custom handlers with client tracking
        handlers = [
            (r"/", IndexHandler, dict(loop=None, policy=None, host_keys_settings=None)),
            (r"/ws", WsockHandler, dict(loop=None, policy=None, host_keys_settings=None))
        ]
        
        # Initialize Tornado application with more compatible settings
        app = tornado.web.Application(handlers, **settings)
        # Create server with explicit parameters to avoid 'wpintvl' error
        import socket
        from tornado.httpserver import HTTPServer
        self.server = HTTPServer(app)
        self.server.listen(self.port, address='0.0.0.0')
        self.ioloop = tornado.ioloop.IOLoop.current()
        
        # Start the server in a separate thread
        self.thread = threading.Thread(target=self._start_server, daemon=True)
        self.thread.start()
        
        self.initialized = True
        _logger.info(f"WebSSH server started on port {self.port}")
        return self.port
    
    def _start_server(self):
        """Start the Tornado IOLoop in a separate thread"""
        self.ioloop.start()
    
    def stop(self):
        """Stop the WebSSH server"""
        if not self.initialized:
            return
        
        if self.server:
            self.server.stop()
            self.ioloop.add_callback(self.ioloop.stop)
            self.thread.join(timeout=5)
            self.initialized = False
            _logger.info("WebSSH server stopped")
    
    def register_client(self, client_id, ssh_client):
        """Register a new SSH client"""
        self.clients[client_id] = ssh_client
        _logger.info(f"Registered SSH client {client_id}")
    
    def unregister_client(self, client_id):
        """Unregister an SSH client"""
        if client_id in self.clients:
            del self.clients[client_id]
            _logger.info(f"Unregistered SSH client {client_id}")


class SSHClientWebSSH(models.Model):
    _inherit = 'ssh.client'
    
    use_webssh = fields.Boolean(string="Use WebSSH Terminal", default=True,
                               help="Use the WebSSH terminal interface for interactive sessions")
    
    webssh_url = fields.Char(string="WebSSH URL", compute="_compute_webssh_url", store=False)
    
    @api.depends()
    def _compute_webssh_url(self):
        """Compute the WebSSH URL for this client"""
        webssh_server = WebSSHServer()
        port = webssh_server.initialize()
        
        for client in self:
            base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
            
            # Create token with connection info
            token_data = {
                'id': client.id,
                'host': client.hostname,
                'port': client.port,
                'username': client.username,
                'password': client.password if client.auth_method == 'password' else '',
                'key_filename': '',  # We'll handle keys separately
                'timestamp': datetime.now().isoformat()
            }
            
            # Base64 encode the token
            token = base64.urlsafe_b64encode(json.dumps(token_data).encode()).decode()
            
            # Build the URL - in production we'd need to properly handle WebSocket URL
            # For local development, we'll use the direct port
            if base_url.startswith('https'):
                protocol = 'wss'
            else:
                protocol = 'ws'
                
            domain = base_url.split('//')[1]
            client.webssh_url = f"{protocol}://{domain}/webssh/?token={token}"
    
    def create_temp_key_file(self):
        """Create a temporary file with the SSH key if using key authentication"""
        if self.auth_method != 'key' or not self.private_key:
            return None
        
        # Create a temporary file to store the key
        fd, path = tempfile.mkstemp()
        try:
            with os.fdopen(fd, 'w') as tmp:
                tmp.write(self.private_key)
            return path
        except Exception as e:
            _logger.error(f"Failed to create temporary key file: {e}")
            os.unlink(path)
            return None
    
    def get_webssh_connection(self):
        """Initialize the WebSSH connection for this client"""
        webssh_server = WebSSHServer()
        port = webssh_server.initialize()
        
        # Register this client with the WebSSH server
        webssh_server.register_client(self.id, self)
        
        # Return the URL for the frontend
        self._compute_webssh_url()
        
        return {
            'url': self.webssh_url,
            'port': port
        }
    
    def stop_webssh_server(self):
        """Stop the WebSSH server - useful for clean shutdown"""
        webssh_server = WebSSHServer()
        webssh_server.stop()
        return True