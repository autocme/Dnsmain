import json
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

class DockerNetwork(models.Model):
    _name = 'docker.network'
    _description = 'Docker Network'
    _order = 'name'
    # Commenting out inheritance until mail module is properly loaded
    # _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Name', required=True,
                     help="Name of the Docker network")
    
    docker_id = fields.Char(string='Network ID', readonly=True,
                          help="Docker network ID")
    
    server_id = fields.Many2one('docker.server', string='Server', required=True,
                              ondelete='cascade',
                              help="Server where this network exists")
    
    active = fields.Boolean(default=True)
    
    # Network details
    driver = fields.Char(string='Driver', readonly=True,
                      help="Network driver (bridge, overlay, etc.)")
    
    scope = fields.Char(string='Scope', readonly=True,
                      help="Network scope (local, swarm, etc.)")
    
    subnet = fields.Char(string='Subnet', readonly=True,
                       help="Network subnet CIDR")
    
    gateway = fields.Char(string='Gateway', readonly=True,
                        help="Network default gateway")
    
    ipv6 = fields.Boolean(string='IPv6 Enabled', readonly=True)
    
    internal = fields.Boolean(string='Internal Network', readonly=True,
                            help="If true, this network can't access the external network")
    
    attachable = fields.Boolean(string='Attachable', readonly=True,
                              help="If true, services can be attached to this network")
    
    ingress = fields.Boolean(string='Ingress', readonly=True,
                           help="If true, this network is the ingress network")
    
    # Related information
    containers = fields.Text(string='Connected Containers', readonly=True)
    
    connected_container_count = fields.Integer(string='Connected Containers', 
                                             compute='_compute_connected_containers',
                                             store=True)
    
    options = fields.Text(string='Options', readonly=True,
                        help="Network driver options")
    
    last_updated = fields.Datetime(string='Last Updated', readonly=True)
    notes = fields.Text(string='Notes')
    
    # Related logs
    log_ids = fields.One2many('docker.logs', 'network_id', string='Logs')
    
    # -------------------------------------------------------------------------
    # Compute methods
    # -------------------------------------------------------------------------
    @api.depends('containers')
    def _compute_connected_containers(self):
        for network in self:
            count = 0
            if network.containers:
                # Simple count of lines
                count = len(network.containers.split('\n'))
            network.connected_container_count = count
    
    # -------------------------------------------------------------------------
    # Action methods
    # -------------------------------------------------------------------------
    def action_refresh(self):
        """Refresh network details"""
        self.ensure_one()
        self._update_network_details()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Network Refresh'),
                'message': _('Network details updated for %s') % self.name,
                'type': 'info',
                'sticky': False,
            }
        }
    
    def action_remove(self):
        """Remove the network"""
        self.ensure_one()
        
        if self.connected_container_count > 0:
            raise UserError(_('Cannot remove network with connected containers.'))
        
        try:
            server = self.server_id
            ssh_client = server.ssh_client_id
            
            if not ssh_client:
                raise UserError(_('No SSH client configured for server %s') % server.name)
            
            # Check for default networks that shouldn't be removed
            if self.name in ['bridge', 'host', 'none']:
                raise UserError(_('Cannot remove default Docker network %s') % self.name)
            
            cmd = f"docker network rm {self.docker_id if self.docker_id else self.name}"
            cmd = server._prepare_docker_command(cmd)
            result = ssh_client.exec_command(cmd)
            
            if self.docker_id in result or self.name in result:
                self.active = False
                self.last_updated = fields.Datetime.now()
                self._create_log_entry('info', 'Network removed')
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Network Removed'),
                        'message': _('Network %s removed successfully') % self.name,
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                self._create_log_entry('error', f'Failed to remove network: {result}')
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Error'),
                        'message': _('Failed to remove network. See logs for details.'),
                        'type': 'warning',
                        'sticky': False,
                    }
                }
                
        except Exception as e:
            self._create_log_entry('error', f'Error removing network: {str(e)}')
            raise UserError(_('Error removing network: %s') % str(e))
    
    def action_inspect(self):
        """Inspect network details"""
        self.ensure_one()
        try:
            server = self.server_id
            ssh_client = server.ssh_client_id
            
            if not ssh_client:
                raise UserError(_('No SSH client configured for server %s') % server.name)
            
            network_reference = self.docker_id if self.docker_id else self.name
            cmd = f"docker network inspect {network_reference}"
            cmd = server._prepare_docker_command(cmd)
            result = ssh_client.exec_command(cmd)
            
            return {
                'name': _('Network Inspection'),
                'type': 'ir.actions.act_window',
                'res_model': 'docker.inspect.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_network_id': self.id,
                    'default_inspect_content': result
                },
            }
                
        except Exception as e:
            self._create_log_entry('error', f'Error inspecting network: {str(e)}')
            raise UserError(_('Error inspecting network: %s') % str(e))
    
    def action_create_container(self):
        """Open wizard to create a container connected to this network"""
        self.ensure_one()
        return {
            'name': _('Create Container on Network'),
            'type': 'ir.actions.act_window',
            'res_model': 'docker.create.container.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_server_id': self.server_id.id,
                'default_network_id': self.id,
                'default_network_name': self.name
            },
        }
    
    def action_connect_container(self):
        """Open wizard to connect a container to this network"""
        self.ensure_one()
        return {
            'name': _('Connect Container to Network'),
            'type': 'ir.actions.act_window',
            'res_model': 'docker.network.connect.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_server_id': self.server_id.id,
                'default_network_id': self.id,
            },
        }
    
    def action_disconnect_container(self):
        """Open wizard to disconnect a container from this network"""
        self.ensure_one()
        return {
            'name': _('Disconnect Container from Network'),
            'type': 'ir.actions.act_window',
            'res_model': 'docker.network.disconnect.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_server_id': self.server_id.id,
                'default_network_id': self.id,
            },
        }
    
    def action_create_network(self):
        """Open wizard to create a new network"""
        self.ensure_one()
        return {
            'name': _('Create Network'),
            'type': 'ir.actions.act_window',
            'res_model': 'docker.create.network.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_server_id': self.server_id.id,
            },
        }
    
    # -------------------------------------------------------------------------
    # Helper methods for network interaction
    # -------------------------------------------------------------------------
    def _update_network_details(self):
        """Update network details from Docker"""
        self.ensure_one()
        
        try:
            server = self.server_id
            ssh_client = server.ssh_client_id
            
            if not ssh_client:
                return False
            
            # Get network details
            network_reference = self.docker_id if self.docker_id else self.name
            cmd = f"docker network inspect {network_reference} --format '{{{{json .}}}}'"
            cmd = server._prepare_docker_command(cmd)
            result = ssh_client.exec_command(cmd)
            
            try:
                if result and '{' in result:
                    network_details = json.loads(result)
                    
                    if isinstance(network_details, list) and network_details:
                        details = network_details[0]
                        
                        # Extract network driver settings
                        self.driver = details.get('Driver', '')
                        self.scope = details.get('Scope', '')
                        
                        # Extract IPAM config
                        ipam = details.get('IPAM', {})
                        ipam_config = ipam.get('Config', [])
                        if ipam_config and isinstance(ipam_config, list) and len(ipam_config) > 0:
                            self.subnet = ipam_config[0].get('Subnet', '')
                            self.gateway = ipam_config[0].get('Gateway', '')
                        
                        # Extract options
                        options = details.get('Options', {})
                        if options:
                            options_info = []
                            for key, value in options.items():
                                options_info.append(f"{key}={value}")
                            
                            if options_info:
                                self.options = '\n'.join(options_info)
                        
                        # Extract network flags
                        self.ipv6 = details.get('EnableIPv6', False)
                        self.internal = details.get('Internal', False)
                        self.attachable = details.get('Attachable', False)
                        self.ingress = details.get('Ingress', False)
                        
                        # Extract connected containers
                        containers = details.get('Containers', {})
                        if containers:
                            container_info = []
                            for container_id, container_data in containers.items():
                                name = container_data.get('Name', 'Unknown')
                                ip_address = container_data.get('IPv4Address', '')
                                
                                container_info.append(f"{name} ({container_id[:12]}): {ip_address}")
                            
                            if container_info:
                                self.containers = '\n'.join(container_info)
                        else:
                            self.containers = False
                        
                        self.last_updated = fields.Datetime.now()
                        self._create_log_entry('info', 'Network details updated')
                        return True
                        
            except json.JSONDecodeError as json_err:
                self._create_log_entry('error', f'Error parsing network details: {str(json_err)}')
            except Exception as e:
                self._create_log_entry('error', f'Error updating network details: {str(e)}')
            
            return False
                
        except Exception as e:
            self._create_log_entry('error', f'Error fetching network details: {str(e)}')
            return False
    
    def _create_log_entry(self, level, message):
        """Create a log entry for the network"""
        self.ensure_one()
        
        self.env['docker.logs'].create({
            'server_id': self.server_id.id,
            'network_id': self.id,
            'level': level,
            'name': message,
            'user_id': self.env.user.id,
        })