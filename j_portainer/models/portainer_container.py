#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import json
import logging

_logger = logging.getLogger(__name__)

class PortainerContainer(models.Model):
    _name = 'j_portainer.container'
    _description = 'Portainer Container'
    _order = 'name'
    
    def write(self, vals):
        """Override write to handle restart policy changes"""
        result = super(PortainerContainer, self).write(vals)
        
        # If restart policy is changed, update it in Portainer
        if 'restart_policy' in vals:
            for record in self:
                try:
                    record.update_restart_policy()
                except Exception as e:
                    _logger.warning(f"Failed to update restart policy for container {record.name}: {str(e)}")
                    # We don't want to block the write operation if the API call fails
                    pass
                    
        return result
    
    name = fields.Char('Name', required=True)
    container_id = fields.Char('Container ID', required=True)
    image = fields.Char('Image', required=True)
    image_id = fields.Char('Image ID')
    always_pull_image = fields.Boolean('Always Pull Image', default=False,
                                    help="Always pull the latest version of the image")
    created = fields.Datetime('Created')
    status = fields.Char('Status')
    state = fields.Selection([
        ('running', 'Running'),
        ('stopped', 'Stopped'),
        ('paused', 'Paused'),
        ('exited', 'Exited'),
        ('restarting', 'Restarting'),
        ('dead', 'Dead'),
        ('created', 'Created'),
    ], string='State', default='created')
    ports = fields.Text('Ports')
    labels = fields.Text('Labels')
    details = fields.Text('Details')
    volumes = fields.Text('Volumes')
    restart_policy = fields.Selection([
        ('no', 'Never'),
        ('always', 'Always'),
        ('on-failure', 'On Failure'),
        ('unless-stopped', 'Unless Stopped')
    ], string='Restart Policy', default='no', help="Container restart policy")
    
    # Network port configuration
    publish_all_ports = fields.Boolean('Publish all exposed ports to random host ports', default=False, help="Publish all exposed ports to random host ports")
                                   
    # Runtime & Resources fields
    privileged = fields.Boolean('Privileged Mode', default=False,
                             help="Give extended privileges to this container")
    init_process = fields.Boolean('Init', default=False,
                               help="Run an init inside the container that forwards signals and reaps processes")
    shm_size = fields.Integer('Shared Memory Size (MB)', default=64,
                           help="Size of /dev/shm in MB")
    memory_reservation = fields.Integer('Memory Reservation (MB)', default=0,
                                     help="Memory soft limit in MB")
    memory_limit = fields.Integer('Memory Limit (MB)', default=0,
                               help="Memory hard limit in MB")
    cpu_limit = fields.Float('Maximum CPU Usage', default=0.0,
                          help="CPU usage limit (e.g., 0.5 for 50% of a CPU)")
                          
    # Linux Capabilities
    cap_audit_control = fields.Boolean('AUDIT_CONTROL', default=False)
    cap_audit_write = fields.Boolean('AUDIT_WRITE', default=False)
    cap_block_suspend = fields.Boolean('BLOCK_SUSPEND', default=False)
    cap_chown = fields.Boolean('CHOWN', default=False)
    cap_dac_override = fields.Boolean('DAC_OVERRIDE', default=False)
    cap_dac_read_search = fields.Boolean('DAC_READ_SEARCH', default=False)
    cap_fowner = fields.Boolean('FOWNER', default=False)
    cap_fsetid = fields.Boolean('FSETID', default=False)
    cap_ipc_lock = fields.Boolean('IPC_LOCK', default=False)
    cap_ipc_owner = fields.Boolean('IPC_OWNER', default=False)
    cap_kill = fields.Boolean('KILL', default=False)
    cap_lease = fields.Boolean('LEASE', default=False)
    cap_linux_immutable = fields.Boolean('LINUX_IMMUTABLE', default=False)
    cap_mac_admin = fields.Boolean('MAC_ADMIN', default=False)
    cap_mac_override = fields.Boolean('MAC_OVERRIDE', default=False)
    cap_mknod = fields.Boolean('MKNOD', default=False)
    cap_net_admin = fields.Boolean('NET_ADMIN', default=False)
    cap_net_bind_service = fields.Boolean('NET_BIND_SERVICE', default=False)
    cap_net_broadcast = fields.Boolean('NET_BROADCAST', default=False)
    cap_net_raw = fields.Boolean('NET_RAW', default=False)
    cap_setfcap = fields.Boolean('SETFCAP', default=False)
    cap_setgid = fields.Boolean('SETGID', default=False)
    cap_setpcap = fields.Boolean('SETPCAP', default=False)
    cap_setuid = fields.Boolean('SETUID', default=False)
    cap_syslog = fields.Boolean('SYSLOG', default=False)
    cap_sys_admin = fields.Boolean('SYS_ADMIN', default=False)
    cap_sys_boot = fields.Boolean('SYS_BOOT', default=False)
    cap_sys_chroot = fields.Boolean('SYS_CHROOT', default=False)
    cap_sys_module = fields.Boolean('SYS_MODULE', default=False)
    cap_sys_nice = fields.Boolean('SYS_NICE', default=False)
    cap_sys_pacct = fields.Boolean('SYS_PACCT', default=False)
    cap_sys_ptrace = fields.Boolean('SYS_PTRACE', default=False)
    cap_sys_rawio = fields.Boolean('SYS_RAWIO', default=False)
    cap_sys_resource = fields.Boolean('SYS_RESOURCE', default=False)
    cap_sys_time = fields.Boolean('SYS_TIME', default=False)
    cap_sys_tty_config = fields.Boolean('SYS_TTY_CONFIG', default=False)
    cap_wake_alarm = fields.Boolean('WAKE_ALARM', default=False)
    get_formatted_volumes = fields.Html('Formatted Volumes', compute='_compute_formatted_volumes')
    get_formatted_ports = fields.Html('Formatted Ports', compute='_compute_formatted_ports')
    
    server_id = fields.Many2one('j_portainer.server', string='Server', required=True, ondelete='cascade')
    environment_id = fields.Integer('Environment ID', required=True)
    environment_name = fields.Char('Environment', required=True)
    stack_id = fields.Many2one('j_portainer.stack', string='Stack', ondelete='set null')
    
    # One2many relationships
    label_ids = fields.One2many('j_portainer.container.label', 'container_id', string='Container Labels')
    volume_ids = fields.One2many('j_portainer.container.volume', 'container_id', string='Volume Mappings')
    network_ids = fields.One2many('j_portainer.container.network', 'container_id', string='Connected Networks')
    env_ids = fields.One2many('j_portainer.container.env', 'container_id', string='Environment Variables')
    port_ids = fields.One2many('j_portainer.container.port', 'container_id', string='Port Mappings')
    
    def _get_api(self):
        """Get API client"""
        return self.env['j_portainer.api']
    
    def get_formatted_labels(self):
        """Get formatted container labels"""
        self.ensure_one()
        if not self.labels:
            return ''
            
        try:
            labels_data = json.loads(self.labels)
            formatted_labels = [f"{key}: {value}" for key, value in labels_data.items()]
            return '\n'.join(formatted_labels)
        except Exception as e:
            _logger.error(f"Error formatting labels: {str(e)}")
            return self.labels
            
    @api.depends('ports')
    def _compute_formatted_ports(self):
        """Compute formatted port mappings HTML table"""
        for record in self:
            if not record.ports:
                record.get_formatted_ports = '<p>No port mappings for this container</p>'
                continue
                
            try:
                ports_data = json.loads(record.ports)
                if not ports_data:
                    record.get_formatted_ports = '<p>No port mappings for this container</p>'
                    continue
                    
                html = ['<table class="table table-sm table-hover">',
                        '<thead>',
                        '<tr>',
                        '<th>Host IP</th>',
                        '<th>Host Port</th>',
                        '<th>Container Port</th>',
                        '<th>Protocol</th>',
                        '</tr>',
                        '</thead>',
                        '<tbody>']
                        
                for port in ports_data:
                    # Extract port mapping data
                    host_ip = port.get('IP', '0.0.0.0')
                    host_port = port.get('PublicPort', '-')
                    container_port = port.get('PrivatePort', '-')
                    protocol = port.get('Type', 'tcp')
                    
                    # Create a row for this port mapping
                    html.append('<tr>')
                    html.append(f'<td>{host_ip}</td>')
                    html.append(f'<td>{host_port}</td>')
                    html.append(f'<td>{container_port}</td>')
                    html.append(f'<td>{protocol}</td>')
                    html.append('</tr>')
                    
                html.append('</tbody>')
                html.append('</table>')
                
                record.get_formatted_ports = ''.join(html)
            except Exception as e:
                _logger.error(f"Error formatting ports for container {record.name}: {str(e)}")
                record.get_formatted_ports = f'<p>Error formatting ports: {str(e)}</p>'
    
    @api.depends('volumes', 'volume_ids')
    def _compute_formatted_volumes(self):
        """Compute formatted container volumes HTML
        
        Note: This method is kept for backward compatibility.
        The preferred approach is to use the structured volume_ids records.
        """
        for record in self:
            # If we have volume mappings in the structured format, use that as primary source
            if record.volume_ids:
                html = [
                    '<div class="alert alert-info">',
                    '<strong>Note:</strong> Volume information is now available in structured format in the table below.',
                    '</div>'
                ]
                record.get_formatted_volumes = ''.join(html)
                continue
                
            # Fall back to the old JSON-based format if no structured records are available
            if not record.volumes:
                record.get_formatted_volumes = '<p>No volumes attached to this container</p>'
                continue
                
            try:
                volumes_data = json.loads(record.volumes)
                if not volumes_data:
                    record.get_formatted_volumes = '<p>No volumes attached to this container</p>'
                    continue
                    
                html = [
                    '<div class="alert alert-warning">',
                    '<strong>Legacy format:</strong> This information is shown in the old format. Please synchronize the container to get the structured volume data.',
                    '</div>',
                    '<table class="table table-sm table-hover">',
                    '<thead>',
                    '<tr>',
                    '<th>Type</th>',
                    '<th>Name/Source</th>',
                    '<th>Container Path</th>',
                    '<th>Mode</th>',
                    '</tr>',
                    '</thead>',
                    '<tbody>'
                ]
                        
                for volume in volumes_data:
                    # Determine volume type
                    source = volume.get('Source', '')
                    if '/var/lib/docker/volumes/' in source:
                        # This is a named volume
                        volume_name = source.split('/var/lib/docker/volumes/')[1].split('/_data')[0]
                        volume_type = 'Named Volume'
                    elif source.startswith('/'):
                        # This is a bind mount
                        volume_name = source
                        volume_type = 'Bind Mount'
                    else:
                        # This is probably a tmpfs or other type
                        volume_name = source if source else 'N/A'
                        volume_type = 'Other'
                        
                    destination = volume.get('Destination', 'N/A')
                    mode = volume.get('Mode', 'N/A')
                    
                    # Create a row for this volume
                    html.append('<tr>')
                    html.append(f'<td>{volume_type}</td>')
                    html.append(f'<td>{volume_name}</td>')
                    html.append(f'<td>{destination}</td>')
                    html.append(f'<td>{mode}</td>')
                    html.append('</tr>')
                    
                html.append('</tbody>')
                html.append('</table>')
                
                record.get_formatted_volumes = ''.join(html)
            except Exception as e:
                _logger.error(f"Error formatting volumes for container {record.name}: {str(e)}")
                record.get_formatted_volumes = f'<p>Error formatting volumes: {str(e)}</p>'
    
    def get_state_color(self):
        """Get color for container state"""
        self.ensure_one()
        colors = {
            'running': 'success',
            'stopped': 'danger',
            'paused': 'warning',
            'exited': 'danger',
            'restarting': 'info',
            'dead': 'danger',
            'created': 'secondary'
        }
        return colors.get(self.state, 'secondary')
    
    def start(self):
        """Start the container"""
        self.ensure_one()
        
        try:
            api = self._get_api()
            result = api.container_action(
                self.server_id.id, self.environment_id, self.container_id, 'start')

            if result:
                # Update container state
                self.write({'state': 'running', 'status': 'Up'})
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Container Started'),
                        'message': _('Container %s started successfully') % self.name,
                        'sticky': False,
                        'type': 'success',
                    }
                }
            else:
                raise UserError(_("Failed to start container"))
        except Exception as e:
            _logger.error(f"Error starting container {self.name}: {str(e)}")
            raise UserError(_("Error starting container: %s") % str(e))
    
    def stop(self):
        """Stop the container"""
        self.ensure_one()
        
        try:
            api = self._get_api()
            result = api.container_action(
                self.server_id.id, self.environment_id, self.container_id, 'stop')
                
            if result:
                # Update container state
                self.write({'state': 'stopped', 'status': 'Stopped'})
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Container Stopped'),
                        'message': _('Container %s stopped successfully') % self.name,
                        'sticky': False,
                        'type': 'success',
                    }
                }
            else:
                raise UserError(_("Failed to stop container"))
        except Exception as e:
            _logger.error(f"Error stopping container {self.name}: {str(e)}")
            raise UserError(_("Error stopping container: %s") % str(e))
    
    def restart(self):
        """Restart the container"""
        self.ensure_one()
        
        try:
            api = self._get_api()
            result = api.container_action(
                self.server_id.id, self.environment_id, self.container_id, 'restart')
                
            if result:
                # Update container state
                self.write({'state': 'running', 'status': 'Up'})
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Container Restarted'),
                        'message': _('Container %s restarted successfully') % self.name,
                        'sticky': False,
                        'type': 'success',
                    }
                }
            else:
                raise UserError(_("Failed to restart container"))
        except Exception as e:
            _logger.error(f"Error restarting container {self.name}: {str(e)}")
            raise UserError(_("Error restarting container: %s") % str(e))
    
    def pause(self):
        """Pause the container"""
        self.ensure_one()
        
        try:
            api = self._get_api()
            result = api.container_action(
                self.server_id.id, self.environment_id, self.container_id, 'pause')
                
            if result:
                # Update container state
                self.write({'state': 'paused', 'status': 'Paused'})
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Container Paused'),
                        'message': _('Container %s paused successfully') % self.name,
                        'sticky': False,
                        'type': 'success',
                    }
                }
            else:
                raise UserError(_("Failed to pause container"))
        except Exception as e:
            _logger.error(f"Error pausing container {self.name}: {str(e)}")
            raise UserError(_("Error pausing container: %s") % str(e))
    
    def unpause(self):
        """Unpause the container"""
        self.ensure_one()
        
        try:
            api = self._get_api()
            result = api.container_action(
                self.server_id.id, self.environment_id, self.container_id, 'unpause')
                
            if result:
                # Update container state
                self.write({'state': 'running', 'status': 'Up'})
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Container Unpaused'),
                        'message': _('Container %s unpaused successfully') % self.name,
                        'sticky': False,
                        'type': 'success',
                    }
                }
            else:
                raise UserError(_("Failed to unpause container"))
        except Exception as e:
            _logger.error(f"Error unpausing container {self.name}: {str(e)}")
            raise UserError(_("Error unpausing container: %s") % str(e))
    
    def kill(self):
        """Kill the container"""
        self.ensure_one()
        
        try:
            api = self._get_api()
            result = api.container_action(
                self.server_id.id, self.environment_id, self.container_id, 'kill')
                
            if result:
                # Update container state
                self.write({'state': 'stopped', 'status': 'Killed'})
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Container Killed'),
                        'message': _('Container %s killed successfully') % self.name,
                        'sticky': False,
                        'type': 'success',
                    }
                }
            else:
                raise UserError(_("Failed to kill container"))
        except Exception as e:
            _logger.error(f"Error killing container {self.name}: {str(e)}")
            raise UserError(_("Error killing container: %s") % str(e))
            
    def update_restart_policy(self):
        """Update the container restart policy in Portainer"""
        self.ensure_one()
        
        try:
            api = self._get_api()
            
            # Prepare restart policy data
            restart_policy = {
                'Name': self.restart_policy
            }
            
            # For on-failure policy, we can add MaximumRetryCount
            # In this implementation, we default to 3 retries, but this could be made configurable
            if self.restart_policy == 'on-failure':
                restart_policy['MaximumRetryCount'] = 3
                
            # Prepare update data for container
            update_data = {
                'RestartPolicy': restart_policy
            }
            
            # Call the API to update the container
            result = api.container_action(
                self.server_id.id, self.environment_id, self.container_id, 'update', 
                params=update_data)
                
            if result and (not isinstance(result, dict) or (isinstance(result, dict) and not result.get('error'))):
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Restart Policy Updated'),
                        'message': _('Restart policy for container %s updated successfully') % self.name,
                        'sticky': False,
                        'type': 'success',
                    }
                }
            else:
                error_msg = result.get('error', _("Failed to update restart policy")) if isinstance(result, dict) else _("Failed to update restart policy")
                raise UserError(error_msg)
        except Exception as e:
            _logger.error(f"Error updating restart policy for container {self.name}: {str(e)}")
            raise UserError(_("Error updating restart policy: %s") % str(e))
            
    def sync_env_vars(self):
        """Synchronize container environment variables with Portainer"""
        self.ensure_one()
        
        try:
            api = self._get_api()
            
            # Inspect container to get current environment variables
            inspect_result = api.container_action(
                self.server_id.id, self.environment_id, self.container_id, 'inspect')
                
            if not inspect_result or isinstance(inspect_result, dict) and inspect_result.get('error'):
                error_msg = inspect_result.get('error', _("Failed to inspect container")) if isinstance(inspect_result, dict) else _("Failed to inspect container")
                raise UserError(error_msg)
                
            # Extract environment variables
            env_vars = inspect_result.get('Config', {}).get('Env', [])
            print('env_vars', env_vars)
            # First, remove existing env vars to avoid duplicates
            self.env_ids.unlink()
            
            # Create new env records
            env_records = []
            for env_var in env_vars:
                if '=' in env_var:
                    name, value = env_var.split('=', 1)
                    env_records.append({
                        'container_id': self.id,
                        'name': name,
                        'value': value
                    })
                else:
                    # Handle case where there's no value
                    env_records.append({
                        'container_id': self.id,
                        'name': env_var,
                        'value': False
                    })
                
            if env_records:
                self.env['j_portainer.container.env'].create(env_records)
                
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Environment Variables Synchronized'),
                    'message': _('Environment variables for container %s synchronized successfully') % self.name,
                    'sticky': False,
                    'type': 'success',
                }
            }
                
        except Exception as e:
            _logger.error(f"Error synchronizing environment variables for container {self.name}: {str(e)}")
            raise UserError(_("Error synchronizing environment variables: %s") % str(e))
            
    def sync_port_mappings(self):
        """Synchronize container port mappings with Portainer
        
        Note: In Docker, updating port mappings requires recreating the container.
        This function will notify the user about the need to recreate the container.
        """
        self.ensure_one()
        
        try:
            # Format the port mappings for display in a message
            port_list = []
            for port in self.port_ids:
                if port.host_port:
                    if port.host_ip:
                        port_list.append(f"{port.host_ip}:{port.host_port}->{port.container_port}/{port.protocol}")
                    else:
                        port_list.append(f"{port.host_port}->{port.container_port}/{port.protocol}")
                else:
                    port_list.append(f"{port.container_port}/{port.protocol} (not published)")
            
            port_str = "\n".join(port_list) if port_list else "No port mappings defined"
            
            # For now, just show a notification that this would require container recreation
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Port Mappings Ready to Update'),
                    'message': _('Container %s would need to be recreated to update port mappings. Current mappings:\n%s') % (self.name, port_str),
                    'sticky': True,
                    'type': 'warning',
                }
            }
                
        except Exception as e:
            _logger.error(f"Error synchronizing port mappings for container {self.name}: {str(e)}")
            raise UserError(_("Error synchronizing port mappings: %s") % str(e))

    def remove(self, force=False, volumes=False):
        """Remove the container
        
        Args:
            force (bool): Force removal
            volumes (bool): Remove volumes associated with the container
            
        Returns:
            dict: Action result
            
        Raises:
            UserError: If container removal fails
        """
        self.ensure_one()
        
        try:
            api = self._get_api()
            result = api.remove_container(
                self.server_id.id, self.environment_id, self.container_id,
                force=force, volumes=volumes)
            
            if isinstance(result, dict) and 'success' in result:
                if result['success']:
                    # Delete the record
                    self.unlink()
                    self.env.cr.commit()

                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Container Removed'),
                            'message': _('Container %s removed successfully') % self.name,
                            'sticky': False,
                            'type': 'success',
                        }
                    }
                else:
                    # API returned failure with message
                    error_message = result.get('message', _("Failed to remove container"))
                    _logger.error(f"Failed to remove container {self.name}: {error_message}")
                    raise UserError(error_message)
            elif result:
                # Legacy boolean True result
                self.unlink()
                self.env.cr.commit()
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Container Removed'),
                        'message': _('Container %s removed successfully') % self.name,
                        'sticky': False,
                        'type': 'success',
                    }
                }
            else:
                # Legacy boolean False result
                raise UserError(_("Failed to remove container"))
        except Exception as e:
            _logger.error(f"Error removing container {self.name}: {str(e)}")
            raise UserError(_("Error removing container: %s") % str(e))
    
    def action_remove_with_options(self):
        """Action to show container removal options"""
        self.ensure_one()
        
        return {
            'name': _('Remove Container'),
            'type': 'ir.actions.act_window',
            'res_model': 'j_portainer.container.remove.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_container_id': self.id,
                'default_container_name': self.name,
            }
        }
    
    def action_refresh(self):
        """Refresh container information"""
        self.ensure_one()
        
        try:
            self.server_id.sync_containers(self.environment_id)
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Container Refreshed'),
                    'message': _('Container information refreshed successfully'),
                    'sticky': False,
                    'type': 'success',
                }
            }
        except Exception as e:
            _logger.error(f"Error refreshing container {self.name}: {str(e)}")
            raise UserError(_("Error refreshing container: %s") % str(e))
    
    def action_view_logs(self):
        """View container logs"""
        self.ensure_one()
        
        return {
            'name': _('Container Logs: %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'j_portainer.container.logs.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_id': self.id,
                'active_model': 'j_portainer.container',
            }
        }
        
    def deploy(self):
        """Deploy a new container with the same configuration as this one"""
        self.ensure_one()
        
        # Get API client
        api = self._get_api()
        
        # New container name (adding -deploy suffix to avoid conflicts)
        container_name = f"{self.name}-deploy"
        
        # Log the deployment attempt
        _logger.info(f"Deploying container based on: {self.name} (Image: {self.image}) to {container_name}")
        
        try:
            # Build config from container fields
            config = {
                'Image': self.image,
                'Hostname': container_name,
                'HostConfig': {
                    'RestartPolicy': {
                        'Name': self.restart_policy or 'no'
                    },
                    'Privileged': self.privileged,
                    'PublishAllPorts': self.publish_all_ports
                }
            }
            
            # Include environment variables if available
            env_vars = self.env['j_portainer.container.env'].search([
                ('container_id', '=', self.id)
            ])
            
            if env_vars:
                env_list = []
                for env in env_vars:
                    if env.value:
                        env_list.append(f"{env.name}={env.value}")
                    else:
                        env_list.append(env.name)
                
                config['Env'] = env_list
            
            # Include port mappings if available
            port_mappings = self.env['j_portainer.container.port'].search([
                ('container_id', '=', self.id)
            ])
            
            if port_mappings:
                exposed_ports = {}
                port_bindings = {}
                
                for port in port_mappings:
                    # Format: port/protocol (e.g., 80/tcp)
                    port_key = f"{port.container_port}/{port.protocol}"
                    
                    # Mark as exposed
                    exposed_ports[port_key] = {}
                    
                    # If host port is specified, add binding
                    if port.host_port:
                        host_ip = port.host_ip or ''
                        if port_key not in port_bindings:
                            port_bindings[port_key] = []
                        
                        port_bindings[port_key].append({
                            'HostIp': host_ip,
                            'HostPort': str(port.host_port)
                        })
                
                # Add to config
                if exposed_ports:
                    config['ExposedPorts'] = exposed_ports
                
                if port_bindings:
                    if 'HostConfig' not in config:
                        config['HostConfig'] = {}
                    config['HostConfig']['PortBindings'] = port_bindings
            
            # Get server object
            server = self.env['j_portainer.server'].browse(self.server_id.id)
            if not server:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Deployment Failed'),
                        'message': _('Server not found'),
                        'sticky': True,
                        'type': 'danger',
                    }
                }
            
            # Set name parameter (Docker API requires name as query parameter)
            params = {'name': container_name}
            
            # Use Docker API endpoint to create container
            _logger.info(f"Creating container with config: {json.dumps(config)}")
            create_endpoint = f'/api/endpoints/{self.environment_id}/docker/containers/create'
            response = server._make_api_request(create_endpoint, 'POST', data=config, params=params)
            
            if response.status_code not in [200, 201, 204]:
                error_msg = f"Failed to create container: {response.text}"
                _logger.error(error_msg)
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Deployment Failed'),
                        'message': error_msg,
                        'sticky': True,
                        'type': 'danger',
                    }
                }
            
            # Parse response to get container ID
            result = response.json()
            container_id = result.get('Id')
            
            if not container_id:
                _logger.error("No container ID in response")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Deployment Failed'),
                        'message': _('No container ID returned from API'),
                        'sticky': True,
                        'type': 'danger',
                    }
                }
            
            # Start the container
            _logger.info(f"Starting container with ID: {container_id}")
            start_endpoint = f'/api/endpoints/{self.environment_id}/docker/containers/{container_id}/start'
            start_response = server._make_api_request(start_endpoint, 'POST')
            
            if start_response.status_code not in [200, 201, 204]:
                error_msg = f"Container created but failed to start: {start_response.text}"
                _logger.warning(error_msg)
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Partial Success'),
                        'message': error_msg,
                        'sticky': True,
                        'type': 'warning',
                    }
                }
            
            # Successfully created and started container
            message = _('Container deployed successfully')
            if container_id:
                message += f" (ID: {container_id[:12]})"
            
            _logger.info(f"Container deployed successfully: {container_id}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Container Deployed'),
                    'message': message,
                    'sticky': False,
                    'type': 'success',
                }
            }
            
        except Exception as e:
            _logger.error(f"Error deploying container {self.name}: {str(e)}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Deployment Error'),
                    'message': _('Error deploying container: %s') % str(e),
                    'sticky': True,
                    'type': 'danger',
                }
            }
        
    def action_join_network(self):
        """Open wizard to join a network"""
        self.ensure_one()
        
        return {
            'name': _('Join Network'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'j_portainer.container.join.network.wizard',
            'target': 'new',
            'context': {
                'default_container_id': self.id,
            }
        }
        

        
    def sync_labels_to_portainer(self):
        """Sync container labels to Portainer"""
        self.ensure_one()
        
        # Get container labels
        labels = self.env['j_portainer.container.label'].search([
            ('container_id', '=', self.id)
        ])
        
        if not labels:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No Labels'),
                    'message': _('This container has no labels to sync'),
                    'sticky': False,
                    'type': 'warning',
                }
            }
            
        # Perform sync
        try:

            # First, log the labels being synced for debugging
            label_dict = {label.name: label.value for label in labels}
            _logger.info(f"Syncing labels for container {self.name}: {label_dict}")
            
            # Perform the sync operation
            result = labels[0]._sync_container_labels_to_portainer(self)
            
            if result:

                # Refresh the container record from Portainer to capture any changes in the container ID
                refreshed = self.action_refresh()
                if isinstance(refreshed, dict) and refreshed.get('params', {}).get('type') == 'danger':
                    _logger.warning(f"Container refresh failed after label sync for container {self.name}")
                    # Even if refresh fails, the label sync was successful
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Labels Synchronized'),
                        'message': _('Container labels have been synced to Portainer successfully. Refresh the page to see any container ID changes.'),
                        'sticky': False,
                        'type': 'success',
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Sync Failed'),
                        'message': _('Failed to sync labels to Portainer. Check server logs for details.'),
                        'sticky': True,
                        'type': 'danger',
                    }
                }
        except Exception as e:
            import traceback
            _logger.error(f"Error syncing container labels: {str(e)}\n{traceback.format_exc()}")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sync Failed'),
                    'message': str(e),
                    'sticky': True,
                    'type': 'danger',
                }
            }