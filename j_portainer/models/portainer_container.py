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
    
    @api.model_create_multi
    def create(self, vals_list):
        """Override create to handle sync operations"""
        # If this is a sync operation from Portainer, save directly
        if self.env.context.get('sync_from_portainer'):
            return super(PortainerContainer, self).create(vals_list)
        
        # For manual creation - not implemented yet as per requirements
        return super(PortainerContainer, self).create(vals_list)
    
    def write(self, vals):
        """Override write to handle changes that need to be synchronized to Portainer"""
        # Store the old name if name is being changed
        old_names = {}
        if 'name' in vals:
            for record in self:
                old_names[record.id] = record.name
        
        # Perform the standard write operation
        result = super(PortainerContainer, self).write(vals)
        
        # Skip sync operations during sync from Portainer
        if self.env.context.get('sync_from_portainer'):
            return result
        
        # If name has changed, update the container name in Portainer
        if 'name' in vals:
            for record in self:
                old_name = old_names.get(record.id, record.name)
                if old_name != record.name and record.container_id:  # Only for existing containers with actual name changes
                    try:
                        _logger.info(f"Updating container name from '{old_name}' to '{record.name}'")
                        record._update_container_name_in_portainer(old_name)
                    except Exception as e:
                        _logger.warning(f"Failed to update container name for container ID {record.container_id}: {str(e)}")
                        # We don't want to block the write operation if the API call fails
                        pass
        
        # If restart policy is changed, update it in Portainer (skip during sync)
        if 'restart_policy' in vals and not self.env.context.get('sync_from_portainer'):
            for record in self:
                try:
                    record.update_restart_policy()
                except Exception as e:
                    _logger.warning(f"Failed to update restart policy for container {record.name}: {str(e)}")
                    # We don't want to block the write operation if the API call fails
                    pass
                    
        return result
    
    name = fields.Char('Name', required=True)
    container_id = fields.Char('Container ID', copy=False)
    image = fields.Char('Image', related='image_id.image_id', readonly=True, store=True)
    image_id = fields.Many2one('j_portainer.image', string='Image', required=True)
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
    
    server_id = fields.Many2one('j_portainer.server', string='Server', required=True, default=lambda self: self._default_server_id())
    environment_id = fields.Many2one('j_portainer.environment', string='Environment', required=True, 
                                    domain="[('server_id', '=', server_id)]", default=lambda self: self._default_environment_id())
    last_sync = fields.Datetime('Last Synchronized', readonly=True)
    stack_id = fields.Many2one('j_portainer.stack', string='Stack', ondelete='set null')
    
    # One2many relationships
    label_ids = fields.One2many('j_portainer.container.label', 'container_id', string='Container Labels')
    volume_ids = fields.One2many('j_portainer.container.volume', 'container_id', string='Volume Mappings')
    network_ids = fields.One2many('j_portainer.container.network', 'container_id', string='Connected Networks')
    env_ids = fields.One2many('j_portainer.container.env', 'container_id', string='Environment Variables')
    port_ids = fields.One2many('j_portainer.container.port', 'container_id', string='Port Mappings')
    
    _sql_constraints = [
        ('unique_container_per_environment', 'unique(server_id, environment_id, container_id)', 
         'Container ID must be unique per environment on each server'),
    ]
    
    @api.model
    def create(self, vals_list):
        """Override create to handle manual creation vs sync operations"""
        if not isinstance(vals_list, list):
            vals_list = [vals_list]
            
        records = self.env['j_portainer.container']
        
        for vals in vals_list:
            # Check if this is a sync operation from Portainer
            if self.env.context.get('sync_from_portainer'):
                # For sync operations, create record directly without triggering Portainer creation
                record = super().create(vals)
                records |= record
            else:
                # For manual creation, create container in Portainer first
                if not vals.get('container_id'):
                    # This is manual creation - create a temporary record to use the creation logic
                    temp_record = super().create(vals)
                    try:
                        # Attempt to create the container in Portainer
                        success = temp_record._create_container_in_portainer()
                        if not success:
                            # If creation failed, delete the temporary record and raise error
                            temp_record.unlink()
                            raise UserError(_("Failed to create container in Portainer"))
                        records |= temp_record
                    except Exception as e:
                        # Clean up temporary record on any error
                        temp_record.unlink()
                        raise UserError(_("Error creating container: %s") % str(e))
                else:
                    # Already has container_id, create normally
                    record = super().create(vals)
                    records |= record
                    
        return records
    

    
    def _default_server_id(self):
        """Default server selection"""
        return self.env['j_portainer.server'].search([('status', '=', 'connected')], limit=1)
    
    def _default_environment_id(self):
        """Default environment selection"""
        # Get the first server and then its first environment
        server = self._default_server_id()
        if server:
            return server.environment_ids[:1]
        return False
    
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
            # Use direct API call to start the container
            server = self.server_id
            start_endpoint = f'/api/endpoints/{self.environment_id.environment_id}/docker/containers/{self.container_id}/start'
            
            # Start container using direct API call
            _logger.info(f"Starting container {self.name} ({self.container_id})")
            response = server._make_api_request(start_endpoint, 'POST')
            
            # Check if start command was accepted (not if it actually worked)
            if response.status_code in [204, 200, 201, 304]:
                # Status 204 is normal - it means "No Content" but the operation was successful
                # Now check if the container is actually running
                running = self._verify_container_running()
                
                if running:
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
                    # Container start command succeeded but container exited right away
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Container Start Issue'),
                            'message': _('Container %s started but exited immediately. Check container logs for details.') % self.name,
                            'sticky': True,
                            'type': 'warning',
                        }
                    }
            else:
                # API returned an error status code
                error_msg = f"API Error: {response.status_code}"
                if hasattr(response, 'text') and response.text:
                    error_msg += f" - {response.text}"
                raise UserError(_(error_msg))
        except Exception as e:
            _logger.error(f"Error starting container {self.name}: {str(e)}")
            raise UserError(_("Error starting container: %s") % str(e))
            
    def _create_container_in_portainer(self):
        """Create a new container in Portainer based on the Odoo record
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Validate required fields
            if not self.name or not self.image_id or not self.server_id or not self.environment_id:
                _logger.error("Cannot create container: missing required fields")
                return False
                
            # Get the server object
            server = self.server_id
            
            # Build container configuration
            config = {
                'Image': self.image_id.repository + ':' + self.image_id.tag if self.image_id else '',
                'Hostname': self.name,
                'HostConfig': {
                    'RestartPolicy': {
                        'Name': self.restart_policy or 'no'
                    },
                    'Privileged': self.privileged,
                    'PublishAllPorts': self.publish_all_ports,
                }
            }
            
            # Include memory limits if set
            if self.memory_limit and self.memory_limit > 0:
                # Convert MB to bytes as required by Docker API
                config['HostConfig']['Memory'] = self.memory_limit * 1024 * 1024
                
            if self.memory_reservation and self.memory_reservation > 0:
                # Convert MB to bytes as required by Docker API 
                config['HostConfig']['MemoryReservation'] = self.memory_reservation * 1024 * 1024
                
            # Include CPU limits if set
            if self.cpu_limit and self.cpu_limit > 0:
                # Docker API expects fractional CPU values
                config['HostConfig']['NanoCpus'] = int(self.cpu_limit * 1000000000)
                
            # Include shared memory size if set
            if self.shm_size and self.shm_size > 0:
                # Convert MB to bytes as required by Docker API
                config['HostConfig']['ShmSize'] = self.shm_size * 1024 * 1024
                
            # Set init process flag if enabled
            if self.init_process:
                config['HostConfig']['Init'] = True
                
            # Add environment variables if available
            env_vars = self.env_ids
            if env_vars:
                env_list = []
                for env in env_vars:
                    if env.value:
                        env_list.append(f"{env.name}={env.value}")
                    else:
                        env_list.append(env.name)
                
                config['Env'] = env_list
                
            # Add port mappings if available
            port_mappings = self.port_ids
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
                    config['HostConfig']['PortBindings'] = port_bindings
                    
            # Add volume mappings if available
            volume_mappings = self.volume_ids
            if volume_mappings:
                binds = []
                volumes = {}
                
                for volume in volume_mappings:
                    # Format host:container:mode
                    if volume.host_path:
                        # Docker API format for binds
                        bind_str = f"{volume.host_path}:{volume.container_path}"
                        if volume.read_only:
                            bind_str += ":ro"
                        binds.append(bind_str)
                    
                    # Mark container path as a volume
                    volumes[volume.container_path] = {}
                
                if binds:
                    config['HostConfig']['Binds'] = binds
                
                if volumes:
                    config['Volumes'] = volumes
                    
            # Add container labels
            container_labels = self.label_ids
            if container_labels:
                labels = {}
                for label in container_labels:
                    labels[label.name] = label.value
                
                config['Labels'] = labels
                
            # Set name parameter (Docker API requires name as query parameter)
            params = {'name': self.name}
            
            # Create the container in Portainer
            _logger.info(f"Creating container {self.name} with image {self.image_id.repository}:{self.image_id.tag}" if self.image_id else f"Creating container {self.name}")
            create_endpoint = f'/api/endpoints/{self.environment_id.environment_id}/docker/containers/create'
            response = server._make_api_request(create_endpoint, 'POST', data=config, params=params)
            
            if response.status_code not in [200, 201, 204]:
                error_msg = f"Failed to create container: {response.text}"
                _logger.error(error_msg)
                return False
                
            # Get the container ID from the response
            result = response.json()
            container_id = result.get('Id')
            
            if not container_id:
                _logger.error("No container ID in response")
                return False
                
            # Update the Odoo record with the container ID
            self.write({'container_id': container_id})
            
            # Start the container if specified
            try:
                # Start the container
                start_endpoint = f'/api/endpoints/{self.environment_id.environment_id}/docker/containers/{container_id}/start'
                start_response = server._make_api_request(start_endpoint, 'POST')
                
                if start_response.status_code in [200, 201, 204]:
                    # Verify container is running
                    self._verify_container_running()
                    _logger.info(f"Container {self.name} started successfully")
                else:
                    _logger.warning(f"Container created but failed to start: {start_response.text}")
            except Exception as e:
                _logger.warning(f"Error starting container: {str(e)}")
                
            return True
                
        except Exception as e:
            _logger.error(f"Error creating container in Portainer: {str(e)}")
            return False
    
    def _update_container_name_in_portainer(self, old_name):
        """Update container name in Portainer
        
        Args:
            old_name (str): The old container name (for logging)
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Get server and API client
            server = self.server_id
            
            # Use Docker API rename endpoint
            rename_endpoint = f'/api/endpoints/{self.environment_id.environment_id}/docker/containers/{self.container_id}/rename'
            
            # Container names in Docker must not include a leading slash
            new_name = self.name.lstrip('/')
            
            # Set query parameters for rename (Docker API expects name as query param)
            params = {'name': new_name}
            
            # Send rename request
            _logger.info(f"Renaming container {old_name} to {new_name} in Portainer")
            response = server._make_api_request(rename_endpoint, 'POST', params=params)
            
            # Check if request was successful
            if response.status_code in [200, 201, 204]:
                _logger.info(f"Successfully renamed container to {new_name} in Portainer")
                return True
            else:
                error_msg = f"Failed to rename container in Portainer: {response.text}"
                _logger.error(error_msg)
                return False
                
        except Exception as e:
            _logger.error(f"Error updating container name in Portainer: {str(e)}")
            return False
            
    def _verify_container_running(self):
        """Verify container is actually running by checking its state directly
        
        Returns:
            bool: True if container is running, False otherwise
        """
        import time
        
        # Wait a moment for container to start (important for containers that might exit immediately)
        time.sleep(1.0)
        
        try:
            # Get container details from Docker API
            server = self.server_id
            endpoint = f'/api/endpoints/{self.environment_id.environment_id}/docker/containers/{self.container_id}/json'
            response = server._make_api_request(endpoint, 'GET')
            
            if response.status_code != 200:
                _logger.warning(f"Failed to verify container state: {response.text}")
                # Don't assume it's running if we can't verify
                self.write({'state': 'unknown', 'status': 'State verification failed'})
                return False
            
            # Get container state from response
            container_data = response.json()
            state = container_data.get('State', {})
            
            # Get humanized status from container
            status_text = container_data.get('State', {}).get('Status', '')
            
            # Get uptime for running containers
            started_at = None
            if state.get('StartedAt'):
                try:
                    # Parse the time string and localize it
                    started_at = state.get('StartedAt')
                except Exception:
                    pass
                    
            # Format status message
            status_message = ''
            
            # Check if container is actually running
            if state.get('Running', False):
                status_message = 'Up'
                if started_at:
                    status_message += f" (since {started_at})"
                    
                self.write({
                    'state': 'running', 
                    'status': status_message
                })
                return True
                
            elif state.get('Restarting', False):
                self.write({
                    'state': 'restarting', 
                    'status': 'Restarting'
                })
                return True
                
            elif state.get('Paused', False):
                self.write({
                    'state': 'paused', 
                    'status': 'Paused'
                })
                return True
                
            else:
                # Container is not running - probably exited with error
                exit_code = state.get('ExitCode', 0)
                error = state.get('Error', '')
                
                if exit_code != 0:
                    # Container exited with error code
                    exit_message = f"Exited ({exit_code})" 
                    
                    # Add error message if available
                    if error:
                        exit_message += f": {error}"
                        
                    # Format message for UI
                    self.write({
                        'state': 'exited',
                        'status': exit_message
                    })
                    
                    # Log details for troubleshooting
                    _logger.warning(f"Container {self.name} started but exited with code {exit_code}: {error}")
                    
                    # Get logs if available for diagnostics
                    try:
                        logs_endpoint = f'/api/endpoints/{self.environment_id.environment_id}/docker/containers/{self.container_id}/logs'
                        logs_params = {'stderr': 1, 'stdout': 1, 'tail': 50}
                        logs_response = server._make_api_request(
                            logs_endpoint, 'GET', 
                            params=logs_params,
                            headers={'Accept': 'text/plain'}
                        )
                        
                        if logs_response.status_code == 200 and logs_response.text:
                            _logger.warning(f"Container logs: {logs_response.text[:1000]}")
                    except Exception as log_error:
                        _logger.error(f"Failed to get container logs: {str(log_error)}")
                        
                    return False
                else:
                    # Container exited with code 0 (normal exit)
                    self.write({
                        'state': 'exited',
                        'status': 'Exited (0)'
                    })
                    return False
        except Exception as e:
            _logger.error(f"Error verifying container state: {str(e)}")
            # Don't assume it's running if verification fails
            self.write({'state': 'unknown', 'status': f'Verification error: {str(e)}'})
            return False
    
    def stop(self):
        """Stop the container"""
        self.ensure_one()
        
        try:
            api = self._get_api()
            result = api.container_action(
                self.server_id.id, self.environment_id.environment_id, self.container_id, 'stop')
                
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
                self.server_id.id, self.environment_id.environment_id, self.container_id, 'restart')
                
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
                self.server_id.id, self.environment_id.environment_id, self.container_id, 'pause')
                
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
                self.server_id.id, self.environment_id.environment_id, self.container_id, 'unpause')
                
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
                self.server_id.id, self.environment_id.environment_id, self.container_id, 'kill')
                
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
                self.server_id.id, self.environment_id.environment_id, self.container_id, 'update', 
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
                self.server_id.id, self.environment_id.environment_id, self.container_id, 'inspect')
                
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

    def _mark_ports_changed(self):
        """Mark container as having port changes that need to be applied to Portainer"""
        self.ensure_one()
        
        # Note: Docker containers require recreation to change port mappings
        # This method will trigger a notification to the user about the required action
        try:
            return self.action_notify_port_changes()
        except Exception as e:
            _logger.warning(f"Failed to handle port changes for container {self.name}: {str(e)}")
            return False

    def action_notify_port_changes(self):
        """Notify user about port changes that require container recreation"""
        self.ensure_one()
        
        if not self.container_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Container Not Found'),
                    'message': _('Container does not exist in Portainer'),
                    'sticky': False,
                    'type': 'warning',
                }
            }
        
        # Build current port mappings from Odoo records
        port_mappings = []
        for port in self.port_ids:
            if port.host_port:
                if port.host_ip:
                    port_mappings.append(f"{port.host_ip}:{port.host_port}->{port.container_port}/{port.protocol}")
                else:
                    port_mappings.append(f"{port.host_port}->{port.container_port}/{port.protocol}")
            else:
                port_mappings.append(f"{port.container_port}/{port.protocol} (exposed only)")
        
        port_list = "\n".join(port_mappings) if port_mappings else "No port mappings"
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Port Changes Detected'),
                'message': _('Port mappings have been updated in Odoo for container "%s".\n\nNew port configuration:\n%s\n\nNote: Docker containers require recreation to apply port changes. Stop the container and recreate it to apply these changes in Portainer.') % (self.name, port_list),
                'sticky': True,
                'type': 'warning',
            }
        }

    def action_recreate_with_new_ports(self):
        """Action to recreate container with updated port mappings"""
        self.ensure_one()
        
        if not self.container_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Container Not Found'),
                    'message': _('Container does not exist in Portainer'),
                    'sticky': False,
                    'type': 'warning',
                }
            }
        
        try:
            # Get container details for recreation
            api = self.env['j_portainer.api']
            
            # First, stop the container if it's running
            if self.state == 'running':
                stop_result = api.container_action(
                    self.server_id.id,
                    'stop',
                    container_id=self.container_id,
                    environment_id=self.environment_id.environment_id
                )
                
                if not stop_result:
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Failed to Stop Container'),
                            'message': _('Could not stop the container before recreation'),
                            'sticky': False,
                            'type': 'danger',
                        }
                    }
            
            # Get container inspection details to preserve configuration
            inspect_response = api.container_action(
                self.server_id.id,
                'inspect',
                container_id=self.container_id,
                environment_id=self.environment_id.environment_id
            )
            
            if not inspect_response or 'error' in inspect_response:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Container Inspection Failed'),
                        'message': _('Could not retrieve container configuration: %s') % inspect_response.get('error', 'Unknown error'),
                        'sticky': False,
                        'type': 'danger',
                    }
                }
            
            # Build new port configuration from Odoo records
            port_bindings = {}
            exposed_ports = {}
            
            for port in self.port_ids:
                port_key = f"{port.container_port}/{port.protocol}"
                exposed_ports[port_key] = {}
                
                if port.host_port:
                    # Published port
                    binding = {
                        'HostIp': port.host_ip or '',
                        'HostPort': str(port.host_port)
                    }
                    port_bindings[port_key] = [binding]
            
            # Store the recreation configuration for manual use
            recreation_config = {
                'container_name': self.name,
                'image': self.image,
                'exposed_ports': exposed_ports,
                'port_bindings': port_bindings,
                'environment_id': self.environment_id.environment_id,
                'original_config': inspect_response,
                'ports_updated': True,
                'timestamp': fields.Datetime.now().isoformat()
            }
            
            # Update container details with recreation info
            self.write({
                'details': json.dumps(recreation_config, indent=2)
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Container Ready for Recreation'),
                    'message': _('Container "%s" has been prepared for recreation with new port mappings.\n\nThe container configuration is saved in the details field. You can now manually recreate the container in Portainer with the updated port configuration.') % self.name,
                    'sticky': True,
                    'type': 'info',
                }
            }
            
        except Exception as e:
            _logger.error(f"Error preparing container recreation for {self.name}: {str(e)}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Recreation Preparation Failed'),
                    'message': _('Error preparing container recreation: %s') % str(e),
                    'sticky': False,
                    'type': 'danger',
                }
            }

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
        
        # Store container name before attempting to delete
        container_name = self.name
        
        try:
            api = self._get_api()
            result = api.remove_container(
                self.server_id.id, self.environment_id.environment_id, self.container_id,
                force=force, volumes=volumes)
            
            # Check for errors in the response
            has_error = False
            error_message = ""
            
            # Handle dictionary response with success/failure indicators
            if isinstance(result, dict) and 'success' in result:
                if not result['success']:
                    has_error = True
                    error_message = result.get('message', _("Failed to remove container"))
            # Handle any non-True, non-dictionary response as an error
            elif not result:
                has_error = True
                error_message = _("Failed to remove container - unexpected response from Portainer")
            
            # If there was an error, raise it and don't delete from Odoo
            if has_error:
                _logger.error(f"Failed to remove container {container_name} from Portainer: {error_message}")
                raise UserError(error_message)
                
            # If we made it here, the removal was successful
            # Log the successful removal
            _logger.info(f"Container {container_name} removed successfully from Portainer")
            
            # Now delete the record
            self.unlink()
            self.env.cr.commit()
            
            # Return nothing, which lets Odoo handle the UI refresh
            
        except Exception as e:
            _logger.error(f"Error removing container {container_name}: {str(e)}")
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
        """Refresh only this container's information directly from Portainer"""
        self.ensure_one()
        
        try:
            # Get the server and environment ID
            server = self.server_id
            environment_id = self.environment_id
            container_id = self.container_id
            
            # Get container details from Portainer API
            _logger.info(f"Refreshing container {self.name} ({container_id})")
            details_endpoint = f'/api/endpoints/{environment_id.environment_id}/docker/containers/{container_id}/json'
            details_response = server._make_api_request(details_endpoint, 'GET')
            
            if details_response.status_code != 200:
                error_msg = f"Failed to get container details: {details_response.text}"
                _logger.error(error_msg)
                raise UserError(error_msg)
                
            # Parse container details
            details = details_response.json()
            
            # Update container information
            update_vals = {}
            
            # Update container name (without leading /)
            container_name = details.get('Name', '')
            if container_name:
                update_vals['name'] = container_name.lstrip('/')
                
            # Update container status and state
            status = details.get('Status', '')
            if status:
                update_vals['status'] = status
                
            # Process state information
            state = details.get('State', {})
            container_state = 'created'
            if state.get('Running'):
                container_state = 'running'
            elif state.get('Paused'):
                container_state = 'paused'
            elif state.get('Restarting'):
                container_state = 'restarting'
            elif state.get('OOMKilled') or state.get('Dead'):
                container_state = 'dead'
            elif state.get('Status') == 'exited':
                container_state = 'exited'
                
            update_vals['state'] = container_state
            
            # Update the container record
            self.write(update_vals)
            
            # Return success notification
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Container Refreshed'),
                    'message': _('Container information updated successfully'),
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
        
        # Use the same container name without any suffix
        container_name = self.name
        
        # Log the deployment attempt
        _logger.info(f"Deploying container based on: {self.name} (Image: {self.image_id.repository}:{self.image_id.tag})" if self.image_id else f"Deploying container based on: {self.name}")
        
        try:
            # Build config from container fields - following exact Portainer format
            config = {
                'Image': self.image_id.repository + ':' + self.image_id.tag if self.image_id else '',
                'Hostname': container_name,
                'HostConfig': {
                    'RestartPolicy': {
                        'Name': self.restart_policy or 'no'
                    },
                    'Privileged': self.privileged,
                    'PublishAllPorts': self.publish_all_ports,
                }
            }
            
            # Include memory limits if set
            if self.memory_limit and self.memory_limit > 0:
                # Convert MB to bytes as required by Docker API
                config['HostConfig']['Memory'] = self.memory_limit * 1024 * 1024
                
            if self.memory_reservation and self.memory_reservation > 0:
                # Convert MB to bytes as required by Docker API 
                config['HostConfig']['MemoryReservation'] = self.memory_reservation * 1024 * 1024
                
            # Include CPU limits if set
            if self.cpu_limit and self.cpu_limit > 0:
                # Docker API expects fractional CPU values
                config['HostConfig']['NanoCpus'] = int(self.cpu_limit * 1000000000)
                
            # Include shared memory size if set
            if self.shm_size and self.shm_size > 0:
                # Convert MB to bytes as required by Docker API
                config['HostConfig']['ShmSize'] = self.shm_size * 1024 * 1024
                
            # Set init process flag if enabled
            if self.init_process:
                config['HostConfig']['Init'] = True
            
            # Container capabilities - exactly like Portainer interface
            cap_add = []
            if self.cap_audit_control: cap_add.append('AUDIT_CONTROL')
            if self.cap_audit_write: cap_add.append('AUDIT_WRITE')
            if self.cap_block_suspend: cap_add.append('BLOCK_SUSPEND')
            if self.cap_chown: cap_add.append('CHOWN')
            if self.cap_dac_override: cap_add.append('DAC_OVERRIDE') 
            if self.cap_dac_read_search: cap_add.append('DAC_READ_SEARCH')
            if self.cap_fowner: cap_add.append('FOWNER')
            if self.cap_fsetid: cap_add.append('FSETID')
            if self.cap_ipc_lock: cap_add.append('IPC_LOCK')
            if self.cap_ipc_owner: cap_add.append('IPC_OWNER')
            if self.cap_kill: cap_add.append('KILL')
            if self.cap_lease: cap_add.append('LEASE')
            if self.cap_linux_immutable: cap_add.append('LINUX_IMMUTABLE')
            if self.cap_mac_admin: cap_add.append('MAC_ADMIN')
            if self.cap_mac_override: cap_add.append('MAC_OVERRIDE')
            if self.cap_mknod: cap_add.append('MKNOD')
            if self.cap_net_admin: cap_add.append('NET_ADMIN')
            if self.cap_net_bind_service: cap_add.append('NET_BIND_SERVICE')
            if self.cap_net_broadcast: cap_add.append('NET_BROADCAST')
            if self.cap_net_raw: cap_add.append('NET_RAW')
            if self.cap_setfcap: cap_add.append('SETFCAP')
            if self.cap_setgid: cap_add.append('SETGID')
            if self.cap_setpcap: cap_add.append('SETPCAP')
            if self.cap_setuid: cap_add.append('SETUID')
            if self.cap_syslog: cap_add.append('SYSLOG')
            if self.cap_sys_admin: cap_add.append('SYS_ADMIN')
            if self.cap_sys_boot: cap_add.append('SYS_BOOT')
            if self.cap_sys_chroot: cap_add.append('SYS_CHROOT')
            if self.cap_sys_module: cap_add.append('SYS_MODULE')
            if self.cap_sys_nice: cap_add.append('SYS_NICE')
            if self.cap_sys_pacct: cap_add.append('SYS_PACCT')
            if self.cap_sys_ptrace: cap_add.append('SYS_PTRACE')
            if self.cap_sys_rawio: cap_add.append('SYS_RAWIO')
            if self.cap_sys_resource: cap_add.append('SYS_RESOURCE')
            if self.cap_sys_time: cap_add.append('SYS_TIME')
            if self.cap_sys_tty_config: cap_add.append('SYS_TTY_CONFIG')
            if self.cap_wake_alarm: cap_add.append('WAKE_ALARM')
            
            if cap_add:
                config['HostConfig']['CapAdd'] = cap_add
            
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
                    config['HostConfig']['PortBindings'] = port_bindings
            
            # Include volume mappings
            volume_mappings = self.env['j_portainer.container.volume'].search([
                ('container_id', '=', self.id)
            ])
            
            if volume_mappings:
                binds = []
                volumes = {}
                
                for volume in volume_mappings:
                    # Format host:container:mode
                    if volume.name:
                        # Docker API format for binds
                        bind_str = f"{volume.name}:{volume.container_path}"
                        if volume.mode == 'ro':
                            bind_str += ":ro"
                        binds.append(bind_str)
                    
                    # Mark container path as a volume
                    volumes[volume.container_path] = {}
                
                if binds:
                    config['HostConfig']['Binds'] = binds
                
                if volumes:
                    config['Volumes'] = volumes
                    
            # Add container labels 
            container_labels = self.env['j_portainer.container.label'].search([
                ('container_id', '=', self.id)
            ])
            
            if container_labels:
                labels = {}
                for label in container_labels:
                    labels[label.name] = label.value
                
                config['Labels'] = labels
            
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
            create_endpoint = f'/api/endpoints/{self.environment_id.environment_id}/docker/containers/create'
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
            
            # Connect to the default bridge network first
            # This ensures the container has at least one network connection
            
            # Get network connections from the source container
            networks = self.env['j_portainer.container.network'].search([
                ('container_id', '=', self.id)
            ])
            
            if networks:
                # Connect the container to the same networks as the source container
                for network in networks:
                    # Make sure we're using the correct network ID from Portainer
                    if not network.network_id:
                        _logger.warning(f"Skipping network connection for {network.network_name}: missing network_id")
                        continue
                        
                    # The network_id in the container.network model is a relation to j_portainer.network
                    # We need to get the Docker network ID from the related network record
                    network_relation = network.network_id
                    if not network_relation:
                        _logger.warning(f"Missing network relation for: {network.network_name}")
                        continue
                    
                    # Get the Docker network ID from the related network record
                    docker_network_id = network_relation.network_id
                    if not docker_network_id or not isinstance(docker_network_id, str):
                        _logger.warning(f"Invalid Docker network ID for: {network.network_name}")
                        continue
                            
                    _logger.info(f"Connecting container to network: {network.network_name} (ID: {docker_network_id})")
                    
                    # Connect the container to the network using the Docker network ID
                    connect_endpoint = f'/api/endpoints/{self.environment_id.environment_id}/docker/networks/{docker_network_id}/connect'
                    connect_payload = {
                        'Container': container_id
                    }
                    
                    try:
                        connect_response = server._make_api_request(connect_endpoint, 'POST', data=connect_payload)
                        
                        if connect_response.status_code not in [200, 201, 204]:
                            _logger.warning(f"Failed to connect container to network {network.network_name}: {connect_response.text}")
                            # Continue with other networks - don't abort the whole operation
                    except Exception as e:
                        _logger.warning(f"Error connecting to network {network.network_name}: {str(e)}")
                        # Continue with other networks
            
            # Start the container
            _logger.info(f"Starting container with ID: {container_id}")
            start_endpoint = f'/api/endpoints/{self.environment_id.environment_id}/docker/containers/{container_id}/start'
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
                
            # Get the new container information to create a record in Odoo
            _logger.info(f"Getting container details for: {container_id}")
            details_endpoint = f'/api/endpoints/{self.environment_id}/docker/containers/{container_id}/json'
            details_response = server._make_api_request(details_endpoint, 'GET')
            
            if details_response.status_code == 200:
                # Create new container record in Odoo
                try:
                    details = details_response.json()
                    
                    # Prepare container data
                    container_name = details.get('Name', '').lstrip('/')
                    state = details.get('State', {})
                    status = details.get('Status', '')
                    
                    # Determine container state
                    container_state = 'created'
                    if state.get('Running'):
                        container_state = 'running'
                    elif state.get('Paused'):
                        container_state = 'paused'
                    elif state.get('Restarting'):
                        container_state = 'restarting'
                    elif state.get('OOMKilled') or state.get('Dead'):
                        container_state = 'dead'
                    elif state.get('Status') == 'exited':
                        container_state = 'exited'
                    elif state.get('Status') == 'created':
                        container_state = 'created'
                    
                    # Format date if available
                    created_at = None
                    if details.get('Created'):
                        try:
                            # Use the date parsing method from PortainerServer
                            created_at = server._parse_date_value(details.get('Created'))
                        except Exception as e:
                            _logger.warning(f"Error parsing created date: {str(e)}")
                    
                    # Create new container record
                    new_container = self.env['j_portainer.container'].create({
                        'name': container_name,
                        'container_id': container_id,
                        'image_id': self.image_id.id,
                        'created': created_at,
                        'status': status,
                        'state': container_state,
                        'restart_policy': self.restart_policy,
                        'privileged': self.privileged,
                        'publish_all_ports': self.publish_all_ports,
                        'server_id': self.server_id.id,
                        'environment_id': self.environment_id.id,
                        'stack_id': self.stack_id.id if self.stack_id else False,
                    })
                    
                    # Successfully created and started container
                    message = _('Container deployed successfully')
                    if container_id:
                        message += f" (ID: {container_id[:12]})"
                    
                    _logger.info(f"Container deployed successfully: {container_id}")
                    
                    # Call the action_refresh method on the new container to update its data
                    try:
                        # Refresh the new container from Portainer
                        _logger.info(f"Refreshing newly deployed container: {new_container.name}")
                        new_container.action_refresh()
                        
                        # Show the newly created container record
                        return {
                            'name': _('Deployed Container'),
                            'type': 'ir.actions.act_window',
                            'res_model': 'j_portainer.container',
                            'res_id': new_container.id,
                            'view_mode': 'form',
                            'view_type': 'form',
                            'target': 'current'
                        }
                    except Exception as e:
                        _logger.error(f"Error syncing containers: {str(e)}")
                        # Fallback to simple notification
                        return {
                            'type': 'ir.actions.client',
                            'tag': 'display_notification',
                            'params': {
                                'title': _('Container Deployed'),
                                'message': message + _(' - Please refresh the container list'),
                                'sticky': False,
                                'type': 'success',
                            }
                        }
                    
                except Exception as e:
                    # If creating Odoo record fails, still return success since container was created in Portainer
                    _logger.error(f"Error creating container record in Odoo: {str(e)}")
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Container Deployed'),
                            'message': _('Container deployed in Portainer but failed to create record in Odoo. Refresh the container list.'),
                            'sticky': True,
                            'type': 'warning',
                        }
                    }
            else:
                # Container was created and started, but we couldn't get its details
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Container Deployed'),
                        'message': _('Container deployed successfully. Please refresh the container list to see it.'),
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