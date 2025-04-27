#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import json
import logging
import re
import base64
import tempfile
import os
from datetime import datetime

# Import the JSON fix functions
from .docker_json_fix import parse_docker_json, clean_docker_output, fix_json_command_output

_logger = logging.getLogger(__name__)

class DockerServer(models.Model):
    _name = 'j_docker.docker_server'
    _description = 'Docker Server'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    
    name = fields.Char('Name', required=True, tracking=True)
    hostname = fields.Char('Hostname', required=True, tracking=True)
    ssh_port = fields.Integer('SSH Port', default=22, tracking=True)
    username = fields.Char('Username', required=True, tracking=True)
    password = fields.Char('Password', tracking=True)
    use_key_auth = fields.Boolean('Use Key Authentication', default=False, tracking=True)
    private_key = fields.Text('Private Key', tracking=True)
    key_file_path = fields.Char('Key File Path', tracking=True)
    key_password = fields.Char('Key Password', tracking=True)
    use_sudo = fields.Boolean('Use sudo', default=False, tracking=True)
    
    status = fields.Selection([
        ('online', 'Online'),
        ('offline', 'Offline'),
        ('error', 'Error')
    ], string='Status', default='offline', readonly=True, tracking=True)
    
    status_details = fields.Text('Status Details', readonly=True, tracking=True)
    last_check = fields.Datetime('Last Status Check', readonly=True)
    docker_version = fields.Char('Docker Version', readonly=True)
    api_version = fields.Char('API Version', readonly=True)
    container_count = fields.Integer('Containers', readonly=True)
    running_container_count = fields.Integer('Running Containers', readonly=True)
    image_count = fields.Integer('Images', readonly=True)
    docker_info = fields.Text('Docker Info', readonly=True)
    engine_features = fields.Html('Engine Features', readonly=True, sanitize=False)
    
    # Compute API features HTML
    api_features_html = fields.Html('API Features', readonly=True, sanitize=False)
    
    container_ids = fields.One2many('j_docker.docker_container', 'server_id', string='Containers')
    image_ids = fields.One2many('j_docker.docker_image', 'server_id', string='Images')
    volume_ids = fields.One2many('j_docker.docker_volume', 'server_id', string='Volumes')
    network_ids = fields.One2many('j_docker.docker_network', 'server_id', string='Networks')
    
    def _get_ssh_client(self):
        """Get a paramiko SSH client configured for this server"""
        self.ensure_one()
        
        from paramiko_ssh_client import ParamikoSshClient
        
        # Determine auth method
        password = self.password if not self.use_key_auth else None
        key_file = self.key_file_path if self.use_key_auth and self.key_file_path else None
        key_data = self.private_key if self.use_key_auth and self.private_key else None
        
        # Create SSH client with enhanced settings
        client = ParamikoSshClient(
            hostname=self.hostname,
            username=self.username,
            port=self.ssh_port,
            password=password,
            key_file=key_file,
            key_data=key_data,
            key_password=self.key_password,
            use_clean_output=True,
            force_minimal_terminal=True,
            connect_timeout=15,
            command_timeout=60,
            retry_count=3,
            retry_delay=2
        )
        
        # Connect to the server
        if client.connect():
            return client
        else:
            _logger.error(f"Failed to connect to {self.hostname}")
            return None
    
    def _run_ssh_command(self, command, timeout=60):
        """Run an SSH command on the server"""
        self.ensure_one()
        
        client = self._get_ssh_client()
        if not client:
            raise UserError(_("Could not connect to server via SSH"))
        
        try:
            return client.execute_command(command, timeout=timeout)
        finally:
            client.disconnect()
    
    def run_docker_command(self, command, as_json=True, timeout=60):
        """
        Run a Docker command with enhanced JSON parsing
        
        Args:
            command (str): Docker command (without 'docker' prefix)
            as_json (bool): Whether to parse output as JSON
            timeout (int): Command timeout in seconds
            
        Returns:
            dict/list: Parsed JSON result or raw output
        """
        self.ensure_one()
        
        # Add docker prefix
        full_command = f"docker {command}"
        
        # Add sudo if needed
        if self.use_sudo:
            full_command = f"sudo {full_command}"
        
        try:
            output = self._run_ssh_command(full_command, timeout=timeout)
            
            # For JSON output, use enhanced parsing
            if as_json:
                try:
                    # Use the enhanced JSON parsing
                    return parse_docker_json(output, full_command)
                except ValueError as e:
                    _logger.error(f"JSON parse error: {str(e)}")
                    _logger.error(f"Raw output preview: {output[:200]}")
                    raise UserError(_("Docker connection failed, JSON parse error: %s") % str(e))
            
            # For non-JSON output, just clean it
            return clean_docker_output(output, full_command)
            
        except Exception as e:
            _logger.error(f"Docker command failed: {str(e)}")
            # Update server status
            self.write({
                'status': 'error',
                'status_details': str(e)
            })
            raise UserError(_("Docker command failed: %s") % str(e))
    
    def check_connection(self):
        """Check Docker server connection with better error handling"""
        self.ensure_one()
        
        try:
            # Run a simple Docker command with JSON output
            command = "info --format '{{json .}}'"
            
            # Use the fixed JSON parsing
            docker_info = self.run_docker_command(command)
            
            # Get version info
            version_cmd = "version --format '{{json .}}'"
            version_info = self.run_docker_command(version_cmd)
            
            # Extract API and Engine versions
            api_version = None
            engine_version = None
            
            if 'Server' in version_info:
                if 'ApiVersion' in version_info['Server']:
                    api_version = version_info['Server']['ApiVersion']
                elif 'Engine' in version_info['Server'] and 'ApiVersion' in version_info['Server']['Engine']:
                    api_version = version_info['Server']['Engine']['ApiVersion']
                    
                if 'Version' in version_info['Server']:
                    engine_version = version_info['Server']['Version']
                elif 'Engine' in version_info['Server'] and 'Version' in version_info['Server']['Engine']:
                    engine_version = version_info['Server']['Engine']['Version']
            
            # Update server status and info
            vals = {
                'status': 'online',
                'status_details': f"Connected to Docker {engine_version or 'unknown'}",
                'last_check': fields.Datetime.now(),
                'docker_version': engine_version or '',
                'api_version': api_version or '',
                'docker_info': json.dumps(docker_info, indent=2)
            }
            
            # Container counts
            if 'Containers' in docker_info:
                vals['container_count'] = docker_info['Containers']
                
            if 'ContainersRunning' in docker_info:
                vals['running_container_count'] = docker_info['ContainersRunning']
                
            # Image count
            if 'Images' in docker_info:
                vals['image_count'] = docker_info['Images']
            
            # Update the server record
            self.write(vals)
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Connection Successful'),
                    'message': _('Successfully connected to Docker server'),
                    'sticky': False,
                    'type': 'success',
                }
            }
            
        except Exception as e:
            # Update server status to error
            self.write({
                'status': 'offline',
                'status_details': str(e),
                'last_check': fields.Datetime.now()
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Connection Failed'),
                    'message': str(e),
                    'sticky': True,
                    'type': 'danger',
                }
            }
    
    def refresh_containers(self):
        """Refresh the list of containers for this server"""
        self.ensure_one()
        
        try:
            # Use run_docker_command with the enhanced parsing
            command = "container ls --all --format '{{json .}}'"
            containers = []
            
            # Get the raw output first
            output = self._run_ssh_command(f"{'sudo ' if self.use_sudo else ''}docker {command}")
            
            # Process each line separately (one JSON object per line)
            for line in output.strip().split('\n'):
                if line.strip():
                    try:
                        # Fix and parse each line
                        fixed_line = fix_json_command_output(line, command)
                        container_data = json.loads(fixed_line)
                        containers.append(container_data)
                    except (ValueError, json.JSONDecodeError) as e:
                        _logger.warning(f"Error parsing container line: {str(e)}")
                        _logger.debug(f"Problem line: {line[:100]}")
                        continue
            
            if not containers:
                _logger.info("No containers found on the server")
                return True
                
            # Log success
            _logger.info(f"Retrieved {len(containers)} containers from server {self.name}")
            
            # Create or update container records
            # Process the containers and update the records
            # (This is where your existing container synchronization code would go)
            
            return True
            
        except Exception as e:
            _logger.error(f"Error refreshing containers: {str(e)}")
            self.write({
                'status': 'error',
                'status_details': f"Container refresh failed: {str(e)}",
                'last_check': fields.Datetime.now()
            })
            raise UserError(_("Failed to refresh containers: %s") % str(e))
    
    # Add methods for other Docker operations using the enhanced parsing...
    
    @api.model
    def create(self, vals):
        """Create record and check connection"""
        server = super(DockerServer, self).create(vals)
        # Optionally check connection on create
        return server
    
    def write(self, vals):
        """Update record and check connection if connection details changed"""
        result = super(DockerServer, self).write(vals)
        
        # Check if we need to verify the connection
        conn_fields = ['hostname', 'ssh_port', 'username', 'password', 
                      'use_key_auth', 'private_key', 'key_file_path', 
                      'key_password', 'use_sudo']
                      
        if any(field in vals for field in conn_fields):
            for server in self:
                server.check_connection()
                
        return result