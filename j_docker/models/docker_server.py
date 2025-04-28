#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import json
import logging
import re
import socket
import datetime
from dateutil import parser

from .docker_json_fix import fix_json_command_output, clean_docker_output

_logger = logging.getLogger(__name__)

class DockerServer(models.Model):
    _name = 'j_docker.docker_server'
    _description = 'Docker Server'
    # Uncomment the following line to add mail support
    # _inherit = ['mail.thread', 'mail.activity.mixin']
    
    name = fields.Char('Name', required=True)
    host = fields.Char('Host', required=True, 
                     help="Hostname or IP address of the server")
    port = fields.Integer('SSH Port', default=22)
    username = fields.Char('Username', required=True)
    
    # Authentication options
    auth_method = fields.Selection([
        ('password', 'Password'),
        ('key', 'SSH Key'),
    ], string='Authentication Method', default='password', required=True)
    
    password = fields.Char('Password')
    private_key = fields.Text('Private Key')
    private_key_password = fields.Char('Private Key Password')
    
    # Docker specific
    docker_socket = fields.Char('Docker Socket', default='/var/run/docker.sock',
                             help="Path to the Docker socket (usually /var/run/docker.sock)")
    use_sudo = fields.Boolean('Use sudo', default=False, 
                           help="Use sudo for Docker commands")
    
    # Server status
    status = fields.Selection([
        ('unknown', 'Unknown'),
        ('connecting', 'Connecting'),
        ('connected', 'Connected'),
        ('error', 'Error'),
    ], string='Status', default='unknown', readonly=True)
    
    last_check = fields.Datetime('Last Check', readonly=True)
    error_message = fields.Text('Error Message', readonly=True)
    
    # Docker info
    docker_version = fields.Char('Docker Version', readonly=True)
    docker_api_version = fields.Char('API Version', readonly=True)
    docker_os = fields.Char('OS', readonly=True)
    docker_arch = fields.Char('Architecture', readonly=True)
    docker_kernel = fields.Char('Kernel Version', readonly=True)
    container_count = fields.Integer('Containers', readonly=True)
    container_running = fields.Integer('Running Containers', readonly=True)
    container_paused = fields.Integer('Paused Containers', readonly=True)
    container_stopped = fields.Integer('Stopped Containers', readonly=True)
    image_count = fields.Integer('Images', readonly=True)
    
    # Related resources
    container_ids = fields.One2many('j_docker.docker_container', 'server_id', string='Containers')
    image_ids = fields.One2many('j_docker.docker_image', 'server_id', string='Images')
    volume_ids = fields.One2many('j_docker.docker_volume', 'server_id', string='Volumes')
    network_ids = fields.One2many('j_docker.docker_network', 'server_id', string='Networks')
    
    # HTML field for Docker API version info
    api_version_info_html = fields.Html('API Version Info', readonly=True,
                                    help="Detailed information about the Docker Engine API version")
    
    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'Server name must be unique!')
    ]
    
    def test_connection(self):
        """Test connection to the Docker server"""
        self.ensure_one()
        
        try:
            self.status = 'connecting'
            self._cr.commit()  # Commit the transaction to update the UI
            
            # Create SSH client
            from . import paramiko_ssh_client
            client = paramiko_ssh_client.ParamikoSSHClient(
                host=self.host,
                port=self.port,
                username=self.username,
                password=self.password if self.auth_method == 'password' else None,
                key=self.private_key if self.auth_method == 'key' else None,
                key_password=self.private_key_password if self.auth_method == 'key' and self.private_key_password else None
            )
            
            # Run a basic Docker command
            command = f"{'sudo ' if self.use_sudo else ''}docker info --format '{{{{json .}}}}'"
            output = client.execute_command(command)
            
            # Process output
            try:
                output = fix_json_command_output(output)
                docker_info = json.loads(output)
                
                # Update server info
                self.write({
                    'status': 'connected',
                    'last_check': fields.Datetime.now(),
                    'error_message': False,
                    'docker_version': docker_info.get('ServerVersion', ''),
                    'docker_api_version': docker_info.get('ApiVersion', ''),
                    'docker_os': docker_info.get('OperatingSystem', ''),
                    'docker_arch': docker_info.get('Architecture', ''),
                    'docker_kernel': docker_info.get('KernelVersion', ''),
                    'container_count': docker_info.get('Containers', 0),
                    'container_running': docker_info.get('ContainersRunning', 0),
                    'container_paused': docker_info.get('ContainersPaused', 0),
                    'container_stopped': docker_info.get('ContainersStopped', 0),
                    'image_count': docker_info.get('Images', 0),
                })
                
                # Generate API version info HTML
                self._generate_api_version_info_html(docker_info)
                
                # Return success message
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Connection Successful'),
                        'message': _(
                            'Successfully connected to Docker server.\n'
                            'Docker version: %s\n'
                            'API version: %s'
                        ) % (docker_info.get('ServerVersion', ''), docker_info.get('ApiVersion', '')),
                        'sticky': False,
                        'type': 'success',
                    }
                }
            except Exception as e:
                _logger.error(f"Error processing Docker info: {str(e)}")
                self.write({
                    'status': 'error',
                    'last_check': fields.Datetime.now(),
                    'error_message': f"Error processing Docker info: {str(e)}"
                })
                raise UserError(_("Error processing Docker info: %s") % str(e))
                
        except Exception as e:
            _logger.error(f"Connection error: {str(e)}")
            self.write({
                'status': 'error',
                'last_check': fields.Datetime.now(),
                'error_message': str(e)
            })
            raise UserError(_("Connection error: %s") % str(e))
            
    def _generate_api_version_info_html(self, docker_info):
        """Generate HTML for Docker API version info"""
        try:
            html = "<div class='docker-api-info'>"
            
            # API Version Section
            html += "<div class='info-section'>"
            html += f"<h3>API Version: {docker_info.get('Server', {}).get('ApiVersion', 'Unknown')}</h3>"
            html += f"<p><b>Engine Version:</b> {docker_info.get('Server', {}).get('Engine', {}).get('Version', 'Unknown')}</p>"
            html += "</div>"
            
            # Server Section
            html += "<div class='info-section'>"
            html += "<h3>Server Information</h3>"
            html += f"<p><b>Version:</b> {docker_info.get('Server', {}).get('Version', 'Unknown')}</p>"
            html += f"<p><b>Engine:</b> {docker_info.get('Server', {}).get('Engine', {}).get('Version', 'Unknown')}</p>"
            html += f"<p><b>OS:</b> {docker_info.get('OperatingSystem', 'Unknown')}</p>"
            html += f"<p><b>Architecture:</b> {docker_info.get('Architecture', 'Unknown')}</p>"
            html += f"<p><b>Kernel Version:</b> {docker_info.get('KernelVersion', 'Unknown')}</p>"
            html += "</div>"
            
            # Container Statistics
            html += "<div class='info-section'>"
            html += "<h3>Container Statistics</h3>"
            html += f"<p><b>Total Containers:</b> {docker_info.get('Containers', '0')}</p>"
            html += f"<p><b>Running:</b> {docker_info.get('ContainersRunning', '0')}</p>"
            html += f"<p><b>Paused:</b> {docker_info.get('ContainersPaused', '0')}</p>"
            html += f"<p><b>Stopped:</b> {docker_info.get('ContainersStopped', '0')}</p>"
            html += "</div>"
            
            # Image Statistics
            html += "<div class='info-section'>"
            html += "<h3>Image Statistics</h3>"
            html += f"<p><b>Total Images:</b> {docker_info.get('Images', '0')}</p>"
            html += "</div>"
            
            html += "</div>"
            
            # Write the HTML
            self.api_version_info_html = html
            
        except Exception as e:
            _logger.error(f"Error generating API version info HTML: {str(e)}")
            self.api_version_info_html = f"<p>Error generating API version info: {str(e)}</p>"
    
    def run_docker_command(self, command, as_json=True):
        """Execute a Docker command on the server and return the result
        
        Args:
            command (str): Docker command to execute (without docker prefix)
            as_json (bool, optional): Whether to parse the output as JSON. Defaults to True.
            
        Returns:
            dict/list/str: Command result, parsed as JSON if as_json=True
        """
        self.ensure_one()
        
        if not command:
            raise UserError(_("No command provided"))
            
        # Create SSH client
        from . import paramiko_ssh_client
        client = paramiko_ssh_client.ParamikoSSHClient(
            host=self.host,
            port=self.port,
            username=self.username,
            password=self.password if self.auth_method == 'password' else None,
            key=self.private_key if self.auth_method == 'key' else None,
            key_password=self.private_key_password if self.auth_method == 'key' and self.private_key_password else None
        )
        
        # Format JSON output if needed
        format_option = ""
        if as_json and not command.endswith('--format \'{{json .}}\'') and not command.endswith('--format "{{json .}}"'):
            # Check if command already contains a format option
            if not '--format' in command:
                format_option = " --format '{{json .}}'"
        
        # Prepend sudo if necessary
        sudo_prefix = 'sudo ' if self.use_sudo else ''
        
        # Run the command
        full_command = f"{sudo_prefix}docker {command}{format_option}"
        output = client.execute_command(full_command)
        
        # Process output
        if as_json:
            try:
                # Clean up the output
                output = fix_json_command_output(output)
                
                # Check if output contains multiple JSON objects (one per line)
                if output.strip().startswith('[') or output.strip().startswith('{'):
                    # Single JSON object or array
                    return json.loads(output)
                else:
                    # Multiple JSON objects (one per line)
                    result = []
                    for line in output.strip().split('\n'):
                        if line.strip():
                            try:
                                result.append(json.loads(line.strip()))
                            except json.JSONDecodeError:
                                # Skip non-JSON lines
                                continue
                    return result
            except json.JSONDecodeError as e:
                _logger.error(f"Error parsing JSON output: {str(e)}")
                _logger.debug(f"Raw output: {output}")
                raise UserError(_("Error parsing JSON output: %s") % str(e))
        
        return output
    
    def refresh_containers(self):
        """Refresh the list of containers on this server"""
        self.ensure_one()
        
        try:
            # Get all containers
            containers = self.run_docker_command("container ls -a")
            
            # Clear existing containers
            self.container_ids.unlink()
            
            # Create new container records
            for container in containers:
                created = container.get('Created', 0)
                # Try to parse the created field if it's a string
                if isinstance(created, str):
                    try:
                        created = parser.parse(created)
                    except Exception:
                        created = datetime.datetime.now()
                else:
                    # It's a timestamp
                    created = datetime.datetime.fromtimestamp(created)
                
                state = 'created'
                if 'State' in container:
                    state_map = {
                        'running': 'running',
                        'exited': 'exited',
                        'paused': 'paused',
                        'restarting': 'restarting',
                        'dead': 'dead',
                        'created': 'created',
                    }
                    state = state_map.get(container.get('State', '').lower(), 'created')
                    
                self.env['j_docker.docker_container'].create({
                    'server_id': self.id,
                    'name': container.get('Names', '').lstrip('/'),
                    'container_id': container.get('ID', ''),
                    'image': container.get('Image', ''),
                    'image_id': container.get('ImageID', ''),
                    'status': container.get('Status', ''),
                    'state': state,
                    'ports': container.get('Ports', ''),
                    'created': created,
                    'command': container.get('Command', ''),
                })
                
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Containers Refreshed'),
                    'message': _('%d containers found') % len(containers),
                    'sticky': False,
                    'type': 'success',
                }
            }
        except Exception as e:
            _logger.error(f"Error refreshing containers: {str(e)}")
            raise UserError(_("Error refreshing containers: %s") % str(e))
    
    def refresh_images(self):
        """Refresh the list of images on this server"""
        self.ensure_one()
        
        try:
            # Get all images
            images = self.run_docker_command("image ls")
            
            # Clear existing images
            self.image_ids.unlink()
            
            # Create new image records
            for image in images:
                repository = image.get('Repository', '')
                tag = image.get('Tag', '')
                if repository == '<none>':
                    repository = image.get('ID', '')[:12]
                    
                created = image.get('Created', 0)
                # Try to parse the created field if it's a string
                if isinstance(created, str):
                    try:
                        created = parser.parse(created)
                    except Exception:
                        created = datetime.datetime.now()
                else:
                    # It's a timestamp
                    created = datetime.datetime.fromtimestamp(created)
                
                self.env['j_docker.docker_image'].create({
                    'server_id': self.id,
                    'repository': repository,
                    'tag': tag,
                    'image_id': image.get('ID', ''),
                    'created': created,
                    'size': image.get('Size', ''),
                })
                
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Images Refreshed'),
                    'message': _('%d images found') % len(images),
                    'sticky': False,
                    'type': 'success',
                }
            }
        except Exception as e:
            _logger.error(f"Error refreshing images: {str(e)}")
            raise UserError(_("Error refreshing images: %s") % str(e))
            
    def refresh_volumes(self):
        """Refresh the list of volumes on this server"""
        self.ensure_one()
        
        try:
            # Get all volumes
            volumes_data = self.run_docker_command("volume ls")
            
            # Clear existing volumes
            self.volume_ids.unlink()
            
            # Create new volume records
            for volume in volumes_data:
                name = volume.get('Name', '')
                
                # Get additional info through inspect
                try:
                    volume_info = self.run_docker_command(f"volume inspect {name}")
                    if isinstance(volume_info, list) and len(volume_info) > 0:
                        volume_info = volume_info[0]
                        
                    created = volume_info.get('CreatedAt', '')
                    # Try to parse the created field
                    if created:
                        try:
                            created = parser.parse(created)
                        except Exception:
                            created = False
                    else:
                        created = False
                    
                    self.env['j_docker.docker_volume'].create({
                        'server_id': self.id,
                        'name': name,
                        'driver': volume.get('Driver', '') or volume_info.get('Driver', ''),
                        'mountpoint': volume_info.get('Mountpoint', ''),
                        'created': created,
                    })
                except Exception as e:
                    _logger.warning(f"Error inspecting volume {name}: {str(e)}")
                    # Create with limited info
                    self.env['j_docker.docker_volume'].create({
                        'server_id': self.id,
                        'name': name,
                        'driver': volume.get('Driver', ''),
                    })
                
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Volumes Refreshed'),
                    'message': _('%d volumes found') % len(volumes_data),
                    'sticky': False,
                    'type': 'success',
                }
            }
        except Exception as e:
            _logger.error(f"Error refreshing volumes: {str(e)}")
            raise UserError(_("Error refreshing volumes: %s") % str(e))
            
    def refresh_networks(self):
        """Refresh the list of networks on this server"""
        self.ensure_one()
        
        try:
            # Get all networks
            networks = self.run_docker_command("network ls")
            
            # Clear existing networks
            self.network_ids.unlink()
            
            # Create new network records
            for network in networks:
                name = network.get('Name', '')
                network_id = network.get('ID', '')
                
                created = network.get('Created', '')
                # Try to parse the created field
                if created:
                    try:
                        if isinstance(created, (int, float)):
                            created = datetime.datetime.fromtimestamp(created)
                        else:
                            created = parser.parse(created)
                    except Exception:
                        created = False
                else:
                    created = False
                
                self.env['j_docker.docker_network'].create({
                    'server_id': self.id,
                    'name': name,
                    'network_id': network_id,
                    'driver': network.get('Driver', ''),
                    'scope': network.get('Scope', ''),
                    'created': created,
                })
                
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Networks Refreshed'),
                    'message': _('%d networks found') % len(networks),
                    'sticky': False,
                    'type': 'success',
                }
            }
        except Exception as e:
            _logger.error(f"Error refreshing networks: {str(e)}")
            raise UserError(_("Error refreshing networks: %s") % str(e))
            
    def refresh_all(self):
        """Refresh all Docker resources"""
        self.ensure_one()
        
        try:
            # Update server info
            self.test_connection()
            
            # Refresh all resources
            self.refresh_containers()
            self.refresh_images()
            self.refresh_volumes()
            self.refresh_networks()
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Refresh Complete'),
                    'message': _('All Docker resources have been refreshed.'),
                    'sticky': False,
                    'type': 'success',
                }
            }
        except Exception as e:
            _logger.error(f"Error refreshing resources: {str(e)}")
            raise UserError(_("Error refreshing resources: %s") % str(e))
            
    def prune_all(self):
        """Prune all Docker resources"""
        self.ensure_one()
        
        try:
            # Prune containers
            self.run_docker_command("container prune -f", as_json=False)
            
            # Prune images
            self.run_docker_command("image prune -a -f", as_json=False)
            
            # Prune volumes
            self.run_docker_command("volume prune -f", as_json=False)
            
            # Prune networks
            self.run_docker_command("network prune -f", as_json=False)
            
            # Prune system
            self.run_docker_command("system prune -f", as_json=False)
            
            # Refresh all resources
            self.refresh_all()
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Prune Complete'),
                    'message': _('All unused Docker resources have been pruned.'),
                    'sticky': False,
                    'type': 'success',
                }
            }
        except Exception as e:
            _logger.error(f"Error pruning resources: {str(e)}")
            raise UserError(_("Error pruning resources: %s") % str(e))