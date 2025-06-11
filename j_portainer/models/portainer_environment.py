#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import json
import logging

_logger = logging.getLogger(__name__)

class PortainerEnvironment(models.Model):
    _name = 'j_portainer.environment'
    _description = 'Portainer Environment'
    _order = 'name'
    
    name = fields.Char('Environment Name', required=True)
    environment_id = fields.Integer('Environment ID', copy=False, readonly=True)
    url = fields.Char('Environment Address', required=True, help="IP address or hostname of the environment")
    status = fields.Selection([
        ('up', 'Up'),
        ('down', 'Down')
    ], string='Status', default='down', readonly=True)
    type = fields.Selection([
        ('1', 'Docker Standalone'),
        ('2', 'Docker Swarm'),
        ('3', 'Edge Agent'),
        ('4', 'Azure ACI'),
        ('5', 'Kubernetes')
    ], string='Environment Type', help="Type of Docker environment", default='1', readonly="environment_id != False")
    public_url = fields.Char('Public URL', readonly=True)
    group_id = fields.Integer('Group ID', readonly=True)
    group_name = fields.Char('Group', readonly=True)
    tags = fields.Char('Tags', readonly=True)
    details = fields.Text('Details', readonly=True)
    active = fields.Boolean('Active', default=True, readonly=True,
                          help="If unchecked, it means this environment no longer exists in Portainer, "
                               "but it's kept in Odoo for reference and to maintain relationships with templates")
    last_sync = fields.Datetime('Last Synchronized', readonly=True)
    
    # Manual creation fields
    connection_method = fields.Selection([
        ('agent', 'Portainer Agent'),
        ('api', 'Docker API'),
        ('socket', 'Docker Socket')
    ], string='Connection Method', default='agent', required=True, readonly="environment_id != False", help="Method to connect to Docker environment")
    docker_command = fields.Text('Docker Command', required=True, help="Command to run the Portainer agent")
    platform = fields.Selection([
        ('linux', 'Linux / Windows WSL'),
        ('windows', 'Windows WCS')
    ], string='Platform', default='linux', required=True, help="Target platform for the agent")
    
    server_id = fields.Many2one('j_portainer.server', string='Server', required=True, default=lambda self: self._default_server_id())
    
    _sql_constraints = [
        ('unique_environment_per_server', 'unique(server_id, environment_id)', 
         'Environment ID must be unique per server'),
    ]
    
    # Count fields
    container_count = fields.Integer('Containers', compute='_compute_resource_counts')
    running_container_count = fields.Integer('Running Containers', compute='_compute_resource_counts')
    image_count = fields.Integer('Images', compute='_compute_resource_counts')
    volume_count = fields.Integer('Volumes', compute='_compute_resource_counts')
    network_count = fields.Integer('Networks', compute='_compute_resource_counts')
    stack_count = fields.Integer('Stacks', compute='_compute_resource_counts')
    
    def _default_server_id(self):
        """Default server selection"""
        return self.env['j_portainer.server'].search([('status', '=', 'connected')], limit=1)
    
    @api.onchange('type', 'platform', 'connection_method')
    def _onchange_docker_command(self):
        """Generate Docker command based on environment type, platform, and connection method"""
        for record in self:
            if record.connection_method == 'agent':
                if record.type == '1':  # Docker Standalone
                    record._generate_standalone_agent_command()
                elif record.type == '2':  # Docker Swarm
                    record._generate_swarm_agent_command()
                else:
                    record.docker_command = ""
            else:
                # For API and Socket connection methods (future implementation)
                record.docker_command = f"Connection via {record.connection_method} - Implementation pending"
    
    def _generate_standalone_agent_command(self):
        """Generate Docker Standalone Agent command"""
        if self.platform == 'linux':
            self.docker_command = """docker run -d \\
  -p 9001:9001 \\
  --name portainer_agent \\
  --restart=always \\
  -v /var/run/docker.sock:/var/run/docker.sock \\
  -v /var/lib/docker/volumes:/var/lib/docker/volumes \\
  -v /:/host \\
  portainer/agent:2.27.4"""
        elif self.platform == 'windows':
            self.docker_command = """docker run -d \\
  -p 9001:9001 \\
  --name portainer_agent \\
  --restart=always \\
  -v C:\\:C:\\host \\
  -v C:\\ProgramData\\docker\\volumes:C:\\ProgramData\\docker\\volumes \\
  -v \\\\.\\pipe\\docker_engine:\\\\.\\pipe\\docker_engine \\
  portainer/agent:2.27.4"""
    
    def _generate_swarm_agent_command(self):
        """Generate Docker Swarm Agent command"""
        if self.platform == 'linux':
            self.docker_command = """docker network create \\
  --driver overlay \\
  portainer_agent_network

docker service create \\
  --name portainer_agent \\
  --network portainer_agent_network \\
  -p 9001:9001/tcp \\
  --mode global \\
  --constraint 'node.platform.os == linux' \\
  --mount type=bind,src=//var/run/docker.sock,dst=/var/run/docker.sock \\
  --mount type=bind,src=//var/lib/docker/volumes,dst=/var/lib/docker/volumes \\
  --mount type=bind,src=//,dst=/host \\
  portainer/agent:2.27.4"""
        elif self.platform == 'windows':
            self.docker_command = """docker network create \\
  --driver overlay \\
  portainer_agent_network && \\
docker service create \\
  --name portainer_agent \\
  --network portainer_agent_network \\
  -p 9001:9001/tcp \\
  --mode global \\
  --constraint 'node.platform.os == windows' \\
  --mount type=npipe,src=\\\\.\\pipe\\docker_engine,dst=\\\\.\\pipe\\docker_engine \\
  --mount type=bind,src=C:\\ProgramData\\docker\\volumes,dst=C:\\ProgramData\\docker\\volumes \\
  portainer/agent:2.27.4"""
    
    @api.model
    def default_get(self, fields_list):
        """Set default values including docker command"""
        result = super().default_get(fields_list)
        
        # Set default docker command for Docker Standalone + Linux platform
        if 'docker_command' in fields_list:
            result['docker_command'] = """docker run -d \\
  -p 9001:9001 \\
  --name portainer_agent \\
  --restart=always \\
  -v /var/run/docker.sock:/var/run/docker.sock \\
  -v /var/lib/docker/volumes:/var/lib/docker/volumes \\
  -v /:/host \\
  portainer/agent:2.27.4"""
        
        return result
    
    def _validate_environment_url(self, url):
        """Validate environment URL format - should be IP:PORT or HOST:PORT"""
        import re
        
        if not url:
            raise UserError(_("Environment address is required"))
        
        if ':' not in url:
            raise UserError(_("Environment address must include port number. Format: <IP>:<PORT> or <HOST>:<PORT>\nExample: 192.168.1.100:9001"))
        
        url_pattern = r'^[a-zA-Z0-9.-]+:\d+$'
        if not re.match(url_pattern, url):
            raise UserError(_("Invalid environment address format. Must be <IP>:<PORT> or <HOST>:<PORT>\nExample: 192.168.1.100:9001"))
        
        try:
            host, port = url.rsplit(':', 1)
            port_num = int(port)
            if not (1 <= port_num <= 65535):
                raise UserError(_("Port number must be between 1 and 65535"))
        except ValueError:
            raise UserError(_("Invalid port number in environment address"))
    
    @api.model
    def create(self, vals):
        """Override create to handle manual environment creation via Portainer API"""
        # Check if this is a manual creation (no environment_id means manual creation)
        if not vals.get('environment_id'):
            # Validate required fields for manual creation
            required_fields = ['name', 'url', 'server_id']
            for field in required_fields:
                if not vals.get(field):
                    raise UserError(_("Field '%s' is required for manual environment creation") % field)
            
            # Get server record
            server = self.env['j_portainer.server'].browse(vals['server_id'])
            if not server:
                raise UserError(_("Server not found"))
            
            if server.status != 'connected':
                raise UserError(_("Server must be connected to create environments"))
            
            # Prepare data for Portainer API (multipart/form-data format)
            # Portainer v2.27.4 endpoint creation types:
            # 1 = Local Docker environment (direct socket/API)
            # 2 = Agent environment (Agent connection)
            # 3 = Azure environment
            # 4 = Edge agent environment
            # 5 = Local Kubernetes Environment
            
            connection_method = vals.get('connection_method', 'agent')
            environment_type = vals.get('type', '1')
            
            # Use regular Agent connection (type 2) for remote agent connections
            if connection_method == 'agent':
                portainer_endpoint_type = 2  # Agent environment
            elif environment_type == '2':  # Docker Swarm - use direct connection
                portainer_endpoint_type = 1  # Local Docker environment
            else:
                portainer_endpoint_type = 1  # Local Docker environment
            
            # Validate URL format before proceeding
            self._validate_environment_url(vals['url'])
            
            # Build form data according to API specification
            # Use the exact URL provided by the user
            user_url = vals['url']
            
            # Format URL correctly based on connection type
            if portainer_endpoint_type == 2:  # Agent environment
                # For Agent environments, use the agent URL with tcp:// prefix
                if not user_url.startswith('tcp://'):
                    api_url = f"tcp://{user_url}"
                else:
                    api_url = user_url
            else:
                # For direct Docker connections, ensure tcp:// prefix if not present
                if not user_url.startswith('tcp://'):
                    api_url = f"tcp://{user_url}"
                else:
                    api_url = user_url
            
            environment_data = {
                'Name': vals['name'],
                'EndpointCreationType': str(portainer_endpoint_type),
                'URL': api_url,
                'GroupID': str(vals.get('group_id', 1))
            }
            
            # For Agent environments (type 2), add TLS parameters
            if portainer_endpoint_type == 2:
                environment_data.update({
                    'TLS': 'true',
                    'TLSSkipVerify': 'true',
                    'TLSSkipClientVerify': 'true'
                })
            
            # Add optional fields only if they have values
            public_url = vals.get('public_url', '').strip()
            if public_url:
                environment_data['PublicURL'] = public_url
            
            try:
                # Create environment in Portainer using multipart/form-data
                response = server._make_api_request('/api/endpoints', 'POST', data=environment_data, use_multipart=True)
                
                if response.status_code not in [200, 201]:
                    # Parse error message from response
                    try:
                        error_data = response.json()
                        error_message = error_data.get('message', response.text)
                        if isinstance(error_data, dict) and 'details' in error_data:
                            error_message += f" Details: {error_data['details']}"
                    except:
                        error_message = response.text if response.text else f"HTTP {response.status_code} error"
                    
                    raise UserError(_("Failed to create environment in Portainer: %s") % error_message)
                
                # Parse successful response
                portainer_env = response.json()
                
                # Update vals with data from Portainer response
                vals.update({
                    'environment_id': portainer_env.get('Id'),
                    'url': portainer_env.get('URL', vals['url']),
                    'status': 'up' if portainer_env.get('Status') == 1 else 'down',
                    'type': str(portainer_env.get('Type', vals.get('type', '1'))),
                    'public_url': portainer_env.get('PublicURL', ''),
                    'group_id': portainer_env.get('GroupId'),
                    'group_name': portainer_env.get('GroupName', ''),
                    'active': True,
                    'last_sync': fields.Datetime.now()
                })
                
            except UserError:
                # Re-raise UserError without modification
                raise
            except Exception as e:
                import logging
                _logger = logging.getLogger(__name__)
                _logger.error(f"Error creating environment in Portainer: {str(e)}")
                
                # If this was an Agent connection and it failed, try direct Docker connection as fallback
                if portainer_endpoint_type == 2 and connection_method == 'agent':
                    try:
                        _logger.info("Agent connection failed, trying direct Docker connection...")
                        
                        # Retry with direct Docker connection (type 1)
                        fallback_data = environment_data.copy()
                        fallback_data['EndpointCreationType'] = '1'  # Direct Docker
                        
                        # For direct Docker, ensure tcp:// URL format
                        fallback_data['URL'] = f"tcp://{user_url}"
                        
                        # Remove Agent-specific TLS parameters for direct connection
                        fallback_data.pop('TLS', None)
                        fallback_data.pop('TLSSkipVerify', None)
                        fallback_data.pop('TLSSkipClientVerify', None)
                        
                        _logger.info(f"Trying direct Docker connection with data: {fallback_data}")
                        
                        response = requests.post(
                            f"{server.url}/api/endpoints",
                            headers=headers,
                            files=fallback_data,
                            timeout=30
                        )
                        
                        if response.status_code in [200, 201]:
                            _logger.info("Direct Docker connection succeeded")
                            portainer_env = response.json()
                            vals.update({
                                'environment_id': portainer_env.get('Id'),
                                'url': portainer_env.get('URL', vals['url']),
                                'status': 'up' if portainer_env.get('Status') == 1 else 'down',
                                'type': str(portainer_env.get('Type', vals.get('type', '1'))),
                                'public_url': portainer_env.get('PublicURL', ''),
                                'group_id': portainer_env.get('GroupId'),
                                'group_name': portainer_env.get('GroupName', ''),
                                'active': True,
                                'last_sync': fields.Datetime.now()
                            })
                        else:
                            error_msg = response.text if hasattr(response, 'text') else str(e)
                            raise UserError(_("Failed to create environment in Portainer: %s") % error_msg)
                            
                    except Exception as fallback_error:
                        _logger.error(f"Fallback direct Docker connection also failed: {str(fallback_error)}")
                        raise UserError(_("Failed to create environment in Portainer: %s") % str(e))
                else:
                    raise UserError(_("Failed to create environment in Portainer: %s") % str(e))
        
        # Create the record in Odoo
        return super().create(vals)
    
    @api.depends()
    def _compute_resource_counts(self):
        """Compute resource counts for each environment"""
        for env in self:
            # Containers
            containers = self.env['j_portainer.container'].search([
                ('server_id', '=', env.server_id.id),
                ('environment_id', '=', env.id)
            ])
            env.container_count = len(containers)
            env.running_container_count = len(containers.filtered(lambda c: c.state == 'running'))
            
            # Images
            env.image_count = self.env['j_portainer.image'].search_count([
                ('server_id', '=', env.server_id.id),
                ('environment_id', '=', env.id)
            ])
            
            # Volumes
            env.volume_count = self.env['j_portainer.volume'].search_count([
                ('server_id', '=', env.server_id.id),
                ('environment_id', '=', env.id)
            ])
            
            # Networks
            env.network_count = self.env['j_portainer.network'].search_count([
                ('server_id', '=', env.server_id.id),
                ('environment_id', '=', env.id)
            ])
            
            # Stacks
            env.stack_count = self.env['j_portainer.stack'].search_count([
                ('server_id', '=', env.server_id.id),
                ('environment_id', '=', env.id)
            ])
    
    def get_type_name(self):
        """Get type name"""
        self.ensure_one()
        type_labels = dict(self._fields['type'].selection)
        return type_labels.get(self.type, 'Unknown')
        
    def get_status_color(self):
        """Get status color"""
        self.ensure_one()
        colors = {
            'up': 'success',
            'down': 'danger'
        }
        return colors.get(self.status, 'secondary')
        
    def get_formatted_tags(self):
        """Get formatted tags"""
        self.ensure_one()
        if not self.tags:
            return ''
            
        return self.tags.replace(',', ', ')
        
    def get_formatted_details(self):
        """Get formatted environment details"""
        self.ensure_one()
        if not self.details:
            return ''
            
        try:
            details_data = json.loads(self.details)
            result = []
            
            # Extract key information
            if 'DockerVersion' in details_data:
                result.append(f"Docker Version: {details_data['DockerVersion']}")
                
            if 'Plugins' in details_data:
                plugins = details_data['Plugins']
                if 'Volume' in plugins and plugins['Volume']:
                    result.append(f"Volume Plugins: {', '.join(plugins['Volume'])}")
                if 'Network' in plugins and plugins['Network']:
                    result.append(f"Network Plugins: {', '.join(plugins['Network'])}")
                    
            if 'SystemStatus' in details_data and details_data['SystemStatus']:
                result.append("System Status:")
                for status in details_data['SystemStatus']:
                    if len(status) >= 2:
                        result.append(f"  {status[0]}: {status[1]}")
                        
            return '\n'.join(result)
        except Exception as e:
            _logger.error(f"Error formatting details: {str(e)}")
            return self.details
    
    def sync_resources(self):
        """Sync all resources for this environment"""
        self.ensure_one()
        
        try:
            # Sync all resources for this environment
            server = self.server_id
            
            server.sync_containers(self.environment_id)
            server.sync_images(self.environment_id)
            server.sync_volumes(self.environment_id)
            server.sync_networks(self.environment_id)
            server.sync_stacks(self.environment_id)
            
            # Recompute counters
            self._compute_resource_counts()
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Environment Synchronized'),
                    'message': _('All resources for environment %s have been synchronized') % self.name,
                    'sticky': False,
                    'type': 'success',
                }
            }
        except Exception as e:
            _logger.error(f"Error syncing environment {self.name}: {str(e)}")
            raise UserError(_("Error syncing environment: %s") % str(e))
    
    def action_view_containers(self):
        """View containers for this environment"""
        self.ensure_one()
        
        return {
            'name': _('Containers - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'j_portainer.container',
            'view_mode': 'tree,form',
            'domain': [
                ('server_id', '=', self.server_id.id),
                ('environment_id', '=', self.id)
            ],
            'context': {
                'default_server_id': self.server_id.id,
                'default_environment_id': self.id,
            }
        }
    
    def action_view_images(self):
        """View images for this environment"""
        self.ensure_one()
        
        return {
            'name': _('Images - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'j_portainer.image',
            'view_mode': 'tree,form',
            'domain': [
                ('server_id', '=', self.server_id.id),
                ('environment_id', '=', self.environment_id)
            ],
            'context': {
                'default_server_id': self.server_id.id,
                'default_environment_id': self.environment_id,
                'default_environment_name': self.name,
            }
        }
    
    def action_view_volumes(self):
        """View volumes for this environment"""
        self.ensure_one()
        
        return {
            'name': _('Volumes - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'j_portainer.volume',
            'view_mode': 'tree,form',
            'domain': [
                ('server_id', '=', self.server_id.id),
                ('environment_id', '=', self.id)
            ],
            'context': {
                'default_server_id': self.server_id.id,
                'default_environment_id': self.id,
            }
        }
    
    def action_view_networks(self):
        """View networks for this environment"""
        self.ensure_one()
        
        return {
            'name': _('Networks - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'j_portainer.network',
            'view_mode': 'tree,form',
            'domain': [
                ('server_id', '=', self.server_id.id),
                ('environment_id', '=', self.environment_id)
            ],
            'context': {
                'default_server_id': self.server_id.id,
                'default_environment_id': self.environment_id,
                'default_environment_name': self.name,
            }
        }
    
    def action_view_stacks(self):
        """View stacks for this environment"""
        self.ensure_one()
        
        return {
            'name': _('Stacks - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'j_portainer.stack',
            'view_mode': 'tree,form',
            'domain': [
                ('server_id', '=', self.server_id.id),
                ('environment_id', '=', self.environment_id)
            ],
            'context': {
                'default_server_id': self.server_id.id,
                'default_environment_id': self.environment_id,
                'default_environment_name': self.name,
            }
        }