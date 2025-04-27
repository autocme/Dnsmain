import json
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

class DockerContainer(models.Model):
    _name = 'docker.container'
    _description = 'Docker Container'
    _order = 'name'
    # Commenting out inheritance until mail module is properly loaded
    # _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Name', required=True, 
                      help="Name of the container")
    
    docker_id = fields.Char(string='Container ID', readonly=True,
                          help="Docker container ID")
    
    server_id = fields.Many2one('docker.server', string='Server', required=True, 
                              ondelete='cascade',
                              help="Server where this container is running")
    
    active = fields.Boolean(default=True)
    
    # Container details
    image = fields.Char(string='Image',
                       help="Docker image used by this container")
    
    status = fields.Selection([
        ('unknown', 'Unknown'),
        ('created', 'Created'),
        ('running', 'Running'),
        ('paused', 'Paused'),
        ('restarting', 'Restarting'),
        ('exited', 'Exited'),
        ('dead', 'Dead')
    ], string='Status', default='unknown')
    
    status_text = fields.Char(string='Status Details', readonly=True)
    
    ports = fields.Char(string='Ports', readonly=True,
                       help="Exposed ports")
    
    created = fields.Datetime(string='Created', readonly=True)
    command = fields.Char(string='Command', readonly=True,
                         help="Command used to start the container")
    
    # Resource usage
    cpu_usage = fields.Float(string='CPU Usage (%)', readonly=True)
    memory_usage = fields.Float(string='Memory Usage (MB)', readonly=True)
    memory_limit = fields.Float(string='Memory Limit (MB)', readonly=True)
    
    # Advanced settings
    environment = fields.Text(string='Environment Variables', readonly=True)
    volumes = fields.Text(string='Mounted Volumes', readonly=True)
    networks = fields.Text(string='Networks', readonly=True)
    labels = fields.Text(string='Labels', readonly=True)
    
    ip_address = fields.Char(string='IP Address', readonly=True)
    restart_policy = fields.Char(string='Restart Policy', readonly=True)
    
    last_updated = fields.Datetime(string='Last Updated', readonly=True)
    notes = fields.Text(string='Notes')
    
    # Related objects
    log_ids = fields.One2many('docker.logs', 'container_id', string='Logs')
    
    # -------------------------------------------------------------------------
    # Action methods
    # -------------------------------------------------------------------------
    def action_refresh(self):
        """Refresh container details"""
        self.ensure_one()
        self._update_container_details()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Container Refresh'),
                'message': _('Container details updated for %s') % self.name,
                'type': 'info',
                'sticky': False,
            }
        }
    
    def action_start(self):
        """Start the container"""
        self.ensure_one()
        if self.status == 'running':
            raise UserError(_('Container is already running'))
        
        try:
            server = self.server_id
            ssh_client = server.ssh_client_id
            
            if not ssh_client:
                raise UserError(_('No SSH client configured for server %s') % server.name)
            
            cmd = f"docker start {self.docker_id}"
            cmd = server._prepare_docker_command(cmd)
            result = ssh_client.exec_command(cmd)
            
            if self.docker_id in result:
                self.status = 'running'
                self.last_updated = fields.Datetime.now()
                self._create_log_entry('info', 'Container started')
                self._update_container_details()
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Container Started'),
                        'message': _('Container %s started successfully') % self.name,
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                self._create_log_entry('error', f'Failed to start container: {result}')
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Error'),
                        'message': _('Failed to start container. See logs for details.'),
                        'type': 'warning',
                        'sticky': False,
                    }
                }
                
        except Exception as e:
            self._create_log_entry('error', f'Error starting container: {str(e)}')
            raise UserError(_('Error starting container: %s') % str(e))
    
    def action_stop(self):
        """Stop the container"""
        self.ensure_one()
        if self.status != 'running':
            raise UserError(_('Container is not running'))
        
        try:
            server = self.server_id
            ssh_client = server.ssh_client_id
            
            if not ssh_client:
                raise UserError(_('No SSH client configured for server %s') % server.name)
            
            cmd = f"docker stop {self.docker_id}"
            cmd = server._prepare_docker_command(cmd)
            result = ssh_client.exec_command(cmd)
            
            if self.docker_id in result:
                self.status = 'exited'
                self.last_updated = fields.Datetime.now()
                self._create_log_entry('info', 'Container stopped')
                self._update_container_details()
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Container Stopped'),
                        'message': _('Container %s stopped successfully') % self.name,
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                self._create_log_entry('error', f'Failed to stop container: {result}')
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Error'),
                        'message': _('Failed to stop container. See logs for details.'),
                        'type': 'warning',
                        'sticky': False,
                    }
                }
                
        except Exception as e:
            self._create_log_entry('error', f'Error stopping container: {str(e)}')
            raise UserError(_('Error stopping container: %s') % str(e))
    
    def action_restart(self):
        """Restart the container"""
        self.ensure_one()
        
        try:
            server = self.server_id
            ssh_client = server.ssh_client_id
            
            if not ssh_client:
                raise UserError(_('No SSH client configured for server %s') % server.name)
            
            cmd = f"docker restart {self.docker_id}"
            cmd = server._prepare_docker_command(cmd)
            result = ssh_client.exec_command(cmd)
            
            if self.docker_id in result:
                self.status = 'running'
                self.last_updated = fields.Datetime.now()
                self._create_log_entry('info', 'Container restarted')
                self._update_container_details()
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Container Restarted'),
                        'message': _('Container %s restarted successfully') % self.name,
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                self._create_log_entry('error', f'Failed to restart container: {result}')
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Error'),
                        'message': _('Failed to restart container. See logs for details.'),
                        'type': 'warning',
                        'sticky': False,
                    }
                }
                
        except Exception as e:
            self._create_log_entry('error', f'Error restarting container: {str(e)}')
            raise UserError(_('Error restarting container: %s') % str(e))
    
    def action_remove(self):
        """Remove the container"""
        self.ensure_one()
        
        try:
            server = self.server_id
            ssh_client = server.ssh_client_id
            
            if not ssh_client:
                raise UserError(_('No SSH client configured for server %s') % server.name)
            
            # Check if container is running
            if self.status == 'running':
                raise UserError(_('Cannot remove a running container. Stop it first.'))
            
            cmd = f"docker rm {self.docker_id}"
            cmd = server._prepare_docker_command(cmd)
            result = ssh_client.exec_command(cmd)
            
            if self.docker_id in result:
                self.active = False
                self.last_updated = fields.Datetime.now()
                self._create_log_entry('info', 'Container removed')
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Container Removed'),
                        'message': _('Container %s removed successfully') % self.name,
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                self._create_log_entry('error', f'Failed to remove container: {result}')
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Error'),
                        'message': _('Failed to remove container. See logs for details.'),
                        'type': 'warning',
                        'sticky': False,
                    }
                }
                
        except Exception as e:
            self._create_log_entry('error', f'Error removing container: {str(e)}')
            raise UserError(_('Error removing container: %s') % str(e))
    
    def action_view_logs(self):
        """View container logs"""
        self.ensure_one()
        try:
            server = self.server_id
            ssh_client = server.ssh_client_id
            
            if not ssh_client:
                raise UserError(_('No SSH client configured for server %s') % server.name)
            
            cmd = f"docker logs --tail 100 {self.docker_id}"
            cmd = server._prepare_docker_command(cmd)
            result = ssh_client.exec_command(cmd)
            
            return {
                'name': _('Container Logs'),
                'type': 'ir.actions.act_window',
                'res_model': 'docker.logs.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_container_id': self.id,
                    'default_log_content': result
                },
            }
                
        except Exception as e:
            self._create_log_entry('error', f'Error viewing logs: {str(e)}')
            raise UserError(_('Error viewing container logs: %s') % str(e))
    
    def action_inspect(self):
        """Inspect container details"""
        self.ensure_one()
        try:
            server = self.server_id
            ssh_client = server.ssh_client_id
            
            if not ssh_client:
                raise UserError(_('No SSH client configured for server %s') % server.name)
            
            cmd = f"docker inspect {self.docker_id}"
            cmd = server._prepare_docker_command(cmd)
            result = ssh_client.exec_command(cmd)
            
            return {
                'name': _('Container Inspection'),
                'type': 'ir.actions.act_window',
                'res_model': 'docker.inspect.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_container_id': self.id,
                    'default_inspect_content': result
                },
            }
                
        except Exception as e:
            self._create_log_entry('error', f'Error inspecting container: {str(e)}')
            raise UserError(_('Error inspecting container: %s') % str(e))
    
    def action_exec(self):
        """Execute command in container"""
        self.ensure_one()
        
        return {
            'name': _('Execute Command'),
            'type': 'ir.actions.act_window',
            'res_model': 'docker.exec.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_container_id': self.id,
            },
        }
    
    # -------------------------------------------------------------------------
    # Helper methods for container interaction
    # -------------------------------------------------------------------------
    def _update_container_details(self):
        """Update container details from Docker"""
        self.ensure_one()
        
        try:
            server = self.server_id
            ssh_client = server.ssh_client_id
            
            if not ssh_client:
                return False
            
            # Get container details
            cmd = f"docker inspect {self.docker_id} --format '{{{{json .}}}}'"
            cmd = server._prepare_docker_command(cmd)
            result = ssh_client.exec_command(cmd)
            
            try:
                if result and '{' in result:
                    container_details = json.loads(result)
                    
                    if isinstance(container_details, list) and container_details:
                        details = container_details[0]
                        
                        # Extract container information
                        config = details.get('Config', {})
                        state = details.get('State', {})
                        network_settings = details.get('NetworkSettings', {})
                        
                        # Update container status
                        container_state = state.get('Status', '').lower()
                        if container_state in ['created', 'running', 'paused', 'restarting', 'exited', 'dead']:
                            self.status = container_state
                        else:
                            self.status = 'unknown'
                        
                        # Update other details
                        self.status_text = state.get('Status', '')
                        self.command = config.get('Cmd', [])
                        if isinstance(self.command, list):
                            self.command = ' '.join(self.command)
                        
                        # Environment variables
                        env_vars = config.get('Env', [])
                        if env_vars:
                            self.environment = '\n'.join(env_vars)
                        
                        # Extract IP address
                        networks = network_settings.get('Networks', {})
                        if networks:
                            first_network = next(iter(networks.values()))
                            self.ip_address = first_network.get('IPAddress', '')
                            
                            # Build networks string
                            networks_info = []
                            for net_name, net_data in networks.items():
                                ip = net_data.get('IPAddress', '')
                                networks_info.append(f"{net_name}: {ip}")
                            
                            if networks_info:
                                self.networks = '\n'.join(networks_info)
                        
                        # Extract mounted volumes
                        mounts = details.get('Mounts', [])
                        if mounts:
                            volumes_info = []
                            for mount in mounts:
                                source = mount.get('Source', '')
                                destination = mount.get('Destination', '')
                                volumes_info.append(f"{source} -> {destination}")
                            
                            if volumes_info:
                                self.volumes = '\n'.join(volumes_info)
                        
                        # Extract restart policy
                        host_config = details.get('HostConfig', {})
                        restart_policy = host_config.get('RestartPolicy', {})
                        restart_name = restart_policy.get('Name', '')
                        restart_max = restart_policy.get('MaximumRetryCount', 0)
                        
                        if restart_name:
                            if restart_name == 'always':
                                self.restart_policy = 'always'
                            elif restart_name == 'unless-stopped':
                                self.restart_policy = 'unless-stopped'
                            elif restart_name == 'on-failure':
                                self.restart_policy = f'on-failure:{restart_max}'
                            else:
                                self.restart_policy = restart_name
                        
                        # Extract labels
                        labels = config.get('Labels', {})
                        if labels:
                            labels_info = []
                            for key, value in labels.items():
                                labels_info.append(f"{key}={value}")
                            
                            if labels_info:
                                self.labels = '\n'.join(labels_info)
                        
                        # Update created time
                        created = details.get('Created', '')
                        if created:
                            # Try to parse the timestamp
                            try:
                                # Note: This is just a simple conversion and may need to be adjusted
                                # based on the exact format returned by Docker
                                created_dt = fields.Datetime.from_string(created.split('.')[0].replace('Z', ''))
                                self.created = created_dt
                            except Exception as date_err:
                                _logger.warning(f"Could not parse created date: {date_err}")
                        
                        # Update resource usage stats
                        self._update_stats()
                        
                        self.last_updated = fields.Datetime.now()
                        self._create_log_entry('info', 'Container details updated')
                        return True
                        
            except json.JSONDecodeError as json_err:
                self._create_log_entry('error', f'Error parsing container details: {str(json_err)}')
            except Exception as e:
                self._create_log_entry('error', f'Error updating container details: {str(e)}')
            
            return False
                
        except Exception as e:
            self._create_log_entry('error', f'Error fetching container details: {str(e)}')
            return False
    
    def _update_stats(self):
        """Update container resource usage statistics"""
        self.ensure_one()
        
        if self.status != 'running':
            return False
            
        try:
            server = self.server_id
            ssh_client = server.ssh_client_id
            
            if not ssh_client:
                return False
            
            # Get container stats
            cmd = f"docker stats {self.docker_id} --no-stream --format '{{{{json .}}}}'"
            cmd = server._prepare_docker_command(cmd)
            result = ssh_client.exec_command(cmd)
            
            try:
                if result and '{' in result:
                    stats = json.loads(result)
                    
                    # Extract CPU usage
                    cpu_text = stats.get('CPUPerc', '0%')
                    if cpu_text:
                        try:
                            # Remove % sign and convert to float
                            self.cpu_usage = float(cpu_text.replace('%', ''))
                        except ValueError:
                            pass
                    
                    # Extract memory usage
                    mem_usage_text = stats.get('MemUsage', '0 / 0')
                    if mem_usage_text and '/' in mem_usage_text:
                        try:
                            usage_parts = mem_usage_text.split('/')
                            
                            # Try to extract memory usage in MB
                            usage_value = usage_parts[0].strip()
                            if 'GiB' in usage_value:
                                # Convert GiB to MiB
                                usage_mb = float(usage_value.replace('GiB', '')) * 1024
                            elif 'MiB' in usage_value:
                                usage_mb = float(usage_value.replace('MiB', ''))
                            elif 'KiB' in usage_value:
                                # Convert KiB to MiB
                                usage_mb = float(usage_value.replace('KiB', '')) / 1024
                            else:
                                usage_mb = 0
                                
                            self.memory_usage = usage_mb
                            
                            # Try to extract memory limit in MB
                            limit_value = usage_parts[1].strip()
                            if 'GiB' in limit_value:
                                # Convert GiB to MiB
                                limit_mb = float(limit_value.replace('GiB', '')) * 1024
                            elif 'MiB' in limit_value:
                                limit_mb = float(limit_value.replace('MiB', ''))
                            elif 'KiB' in limit_value:
                                # Convert KiB to MiB
                                limit_mb = float(limit_value.replace('KiB', '')) / 1024
                            else:
                                limit_mb = 0
                                
                            self.memory_limit = limit_mb
                            
                        except (ValueError, IndexError):
                            pass
                    
                    return True
            except json.JSONDecodeError:
                pass
            except Exception as e:
                _logger.warning(f"Error parsing container stats: {str(e)}")
            
            return False
                
        except Exception as e:
            _logger.error(f"Error fetching container stats: {str(e)}")
            return False
    
    def _create_log_entry(self, level, message):
        """Create a log entry for the container"""
        self.ensure_one()
        
        self.env['docker.logs'].create({
            'server_id': self.server_id.id,
            'container_id': self.id,
            'level': level,
            'name': message,
            'user_id': self.env.user.id,
        })
        
    # -------------------------------------------------------------------------
    # Cron methods
    # -------------------------------------------------------------------------
    @api.model
    def _cron_refresh_containers(self):
        """Refresh all running containers
        Called by scheduled action
        """
        containers = self.search([('active', '=', True), ('status', '=', 'running')])
        for container in containers:
            try:
                container._update_container_details()
                container._update_stats()
                _logger.info(f"Refreshed container info for {container.name}")
            except Exception as e:
                _logger.error(f"Error refreshing container {container.name}: {str(e)}")