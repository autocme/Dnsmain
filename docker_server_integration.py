#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Docker Server Integration Example

This file shows how to integrate the Docker connectivity module with the Odoo Docker server model.
Note: This is an example implementation intended to be incorporated into the j_docker module's Docker
server model.

Features:
1. Enhanced connectivity with automatic retries
2. Connection pooling for better performance
3. Improved error handling and user feedback
4. Health monitoring with detailed diagnostics
"""

# Example of how to integrate into the j_docker Docker server model

"""
from odoo import models, fields, api
from odoo.exceptions import UserError

# Import our Docker connectivity module
from .docker_connectivity import (
    with_docker_connection,
    check_docker_server_health,
    run_docker_command,
    get_docker_version,
    get_docker_info
)

class DockerServer(models.Model):
    _name = 'j_docker.docker_server'
    _description = 'Docker Server'
    
    name = fields.Char(string='Name', required=True)
    hostname = fields.Char(string='Hostname or IP', required=True)
    ssh_port = fields.Integer(string='SSH Port', default=22)
    username = fields.Char(string='Username', required=True)
    password = fields.Char(string='Password')
    use_key_auth = fields.Boolean(string='Use Key Authentication', default=True)
    private_key = fields.Text(string='Private Key')
    use_sudo = fields.Boolean(string='Use sudo', default=False, 
                             help='Use sudo for Docker commands')
    
    # Status fields
    status = fields.Selection([
        ('online', 'Online'),
        ('offline', 'Offline'),
        ('degraded', 'Degraded'),
        ('unknown', 'Unknown')
    ], string='Status', default='unknown', readonly=True)
    
    status_message = fields.Char(string='Status Message', readonly=True)
    last_check = fields.Datetime(string='Last Status Check', readonly=True)
    
    # Docker info fields
    docker_version = fields.Char(string='Docker Version', readonly=True)
    api_version = fields.Char(string='API Version', readonly=True)
    container_count = fields.Integer(string='Containers', readonly=True)
    running_container_count = fields.Integer(string='Running Containers', readonly=True)
    image_count = fields.Integer(string='Images', readonly=True)
    docker_info = fields.Text(string='Docker Info', readonly=True)
    
    # Update these fields from check_health
    def update_server_status(self, status, message=None):
        self.ensure_one()
        self.status = status
        self.status_message = message or ''
        self.last_check = fields.Datetime.now()
    
    @api.model
    def create(self, vals):
        server = super(DockerServer, self).create(vals)
        # Check health on creation
        server.check_health()
        return server
    
    def write(self, vals):
        result = super(DockerServer, self).write(vals)
        # Check health if connection details changed
        connection_fields = ['hostname', 'ssh_port', 'username', 'password', 
                             'use_key_auth', 'private_key']
        if any(field in vals for field in connection_fields):
            for server in self:
                server.check_health()
        return result
    
    def check_health(self):
        self.ensure_one()
        
        try:
            health = check_docker_server_health(self)
            
            # Update status fields
            self.update_server_status(health['status'], health['message'])
            
            # Update version fields
            self.api_version = health['api_version'] or ''
            
            # Update detailed info if available
            if health['details']:
                # Extract useful information
                self.docker_version = health['engine_version'] or ''
                
                # Container counts
                containers = health['details'].get('Containers', 0)
                self.container_count = containers if isinstance(containers, int) else 0
                
                # Running containers
                running = health['details'].get('ContainersRunning', 0)
                if not isinstance(running, int) and isinstance(health['details'].get('Containers'), dict):
                    running = health['details']['Containers'].get('Running', 0)
                self.running_container_count = running if isinstance(running, int) else 0
                
                # Images
                images = health['details'].get('Images', 0)
                self.image_count = images if isinstance(images, int) else 0
                
                # Full info as JSON
                import json
                self.docker_info = json.dumps(health['details'], indent=2)
                
            return health['status'] == 'online'
            
        except Exception as e:
            self.update_server_status('offline', str(e))
            return False
    
    @with_docker_connection(max_retries=2)
    def get_containers(self, client):
        self.ensure_one()
        
        success, result = run_docker_command(
            client, 
            "container ls --all --format '{{json .}}'", 
            format_json=False, 
            use_sudo=self.use_sudo
        )
        
        if not success:
            raise UserError(f"Failed to get containers: {result}")
        
        # The output is one JSON object per line
        containers = []
        for line in result.strip().split('\n'):
            if line:
                try:
                    container = json.loads(line)
                    containers.append(container)
                except json.JSONDecodeError:
                    continue
        
        return containers
    
    @with_docker_connection(max_retries=2)
    def get_images(self, client):
        self.ensure_one()
        
        success, result = run_docker_command(
            client, 
            "image ls --format '{{json .}}'", 
            format_json=False, 
            use_sudo=self.use_sudo
        )
        
        if not success:
            raise UserError(f"Failed to get images: {result}")
        
        # The output is one JSON object per line
        images = []
        for line in result.strip().split('\n'):
            if line:
                try:
                    image = json.loads(line)
                    images.append(image)
                except json.JSONDecodeError:
                    continue
        
        return images
    
    @with_docker_connection(max_retries=2)
    def get_networks(self, client):
        self.ensure_one()
        
        success, result = run_docker_command(
            client, 
            "network ls --format '{{json .}}'", 
            format_json=False, 
            use_sudo=self.use_sudo
        )
        
        if not success:
            raise UserError(f"Failed to get networks: {result}")
        
        # The output is one JSON object per line
        networks = []
        for line in result.strip().split('\n'):
            if line:
                try:
                    network = json.loads(line)
                    networks.append(network)
                except json.JSONDecodeError:
                    continue
        
        return networks
    
    @with_docker_connection(max_retries=2)
    def get_volumes(self, client):
        self.ensure_one()
        
        success, result = run_docker_command(
            client, 
            "volume ls --format '{{json .}}'", 
            format_json=False, 
            use_sudo=self.use_sudo
        )
        
        if not success:
            raise UserError(f"Failed to get volumes: {result}")
        
        # The output is one JSON object per line
        volumes = []
        for line in result.strip().split('\n'):
            if line:
                try:
                    volume = json.loads(line)
                    volumes.append(volume)
                except json.JSONDecodeError:
                    continue
        
        return volumes
    
    @with_docker_connection(max_retries=1, timeout=120)
    def inspect_container(self, client, container_id):
        self.ensure_one()
        
        success, result = run_docker_command(
            client, 
            f"container inspect {container_id}", 
            format_json=True, 
            use_sudo=self.use_sudo
        )
        
        if not success:
            raise UserError(f"Failed to inspect container: {result}")
        
        # Result should be a list with one item
        if isinstance(result, list) and len(result) > 0:
            return result[0]
        return result
    
    @with_docker_connection(max_retries=1)
    def start_container(self, client, container_id):
        self.ensure_one()
        
        success, result = run_docker_command(
            client, 
            f"container start {container_id}", 
            format_json=False, 
            use_sudo=self.use_sudo
        )
        
        if not success:
            raise UserError(f"Failed to start container: {result}")
        
        return True
    
    @with_docker_connection(max_retries=1)
    def stop_container(self, client, container_id):
        self.ensure_one()
        
        success, result = run_docker_command(
            client, 
            f"container stop {container_id}", 
            format_json=False, 
            use_sudo=self.use_sudo
        )
        
        if not success:
            raise UserError(f"Failed to stop container: {result}")
        
        return True
    
    @with_docker_connection(max_retries=1)
    def restart_container(self, client, container_id):
        self.ensure_one()
        
        success, result = run_docker_command(
            client, 
            f"container restart {container_id}", 
            format_json=False, 
            use_sudo=self.use_sudo
        )
        
        if not success:
            raise UserError(f"Failed to restart container: {result}")
        
        return True
    
    @with_docker_connection(max_retries=1)
    def remove_container(self, client, container_id, force=False):
        self.ensure_one()
        
        force_option = "--force" if force else ""
        success, result = run_docker_command(
            client, 
            f"container rm {force_option} {container_id}", 
            format_json=False, 
            use_sudo=self.use_sudo
        )
        
        if not success:
            raise UserError(f"Failed to remove container: {result}")
        
        return True
    
    @with_docker_connection(max_retries=1, timeout=300)
    def pull_image(self, client, image_name):
        self.ensure_one()
        
        success, result = run_docker_command(
            client, 
            f"image pull {image_name}", 
            format_json=False, 
            use_sudo=self.use_sudo,
            timeout=300
        )
        
        if not success:
            raise UserError(f"Failed to pull image: {result}")
        
        return True
    
    @with_docker_connection(max_retries=1)
    def remove_image(self, client, image_id, force=False):
        self.ensure_one()
        
        force_option = "--force" if force else ""
        success, result = run_docker_command(
            client, 
            f"image rm {force_option} {image_id}", 
            format_json=False, 
            use_sudo=self.use_sudo
        )
        
        if not success:
            raise UserError(f"Failed to remove image: {result}")
        
        return True
    
    @with_docker_connection(max_retries=1, timeout=120)
    def get_container_logs(self, client, container_id, tail=100):
        self.ensure_one()
        
        success, result = run_docker_command(
            client, 
            f"container logs --tail={tail} {container_id}", 
            format_json=False, 
            use_sudo=self.use_sudo
        )
        
        if not success:
            raise UserError(f"Failed to get container logs: {result}")
        
        return result
    
    @with_docker_connection(max_retries=2, timeout=30)
    def get_container_stats(self, client, container_id):
        self.ensure_one()
        
        success, result = run_docker_command(
            client, 
            f"container stats --no-stream --format '{{{{json .}}}}' {container_id}", 
            format_json=False, 
            use_sudo=self.use_sudo
        )
        
        if not success:
            raise UserError(f"Failed to get container stats: {result}")
        
        try:
            return json.loads(result.strip())
        except json.JSONDecodeError as e:
            raise UserError(f"Failed to parse container stats: {str(e)}")
    
    @with_docker_connection(max_retries=2)
    def execute_command(self, client, container_id, command):
        self.ensure_one()
        
        # Escape the command for proper shell handling
        import shlex
        escaped_command = ' '.join(shlex.quote(arg) for arg in command.split())
        
        success, result = run_docker_command(
            client, 
            f"container exec {container_id} {escaped_command}", 
            format_json=False, 
            use_sudo=self.use_sudo
        )
        
        if not success:
            raise UserError(f"Failed to execute command in container: {result}")
        
        return result
"""

# This file is a template that demonstrates how to integrate the Docker connectivity module
# with the Odoo Docker server model. The actual implementation would be incorporated
# directly into the j_docker module's Docker server model.

print("Docker Server Integration Template")
print("This file provides an example of how to integrate the Docker connectivity module")
print("with the j_docker.docker_server model for improved Docker connectivity.")