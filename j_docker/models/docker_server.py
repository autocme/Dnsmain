import json
import re
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

class DockerServer(models.Model):
    _name = 'docker.server'
    _description = 'Docker Server'
    _order = 'name'
    # Commenting out inheritance until mail module is properly loaded
    # _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Name', required=True,
                      help="Name of the Docker server")
    
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Company', 
                                default=lambda self: self.env.company)
    
    # Docker connection details
    ssh_client_id = fields.Many2one('nalios.ssh.client', string='SSH Client', 
                                   required=True,
                                   help="SSH Connection used to communicate with this Docker server")
    
    docker_host = fields.Char(string='Docker Host', default='unix:///var/run/docker.sock',
                             help="Docker daemon socket to connect to")
    docker_api_version = fields.Selection([
        ('1.40', 'API v1.40 (Docker 19.x)'),
        ('1.41', 'API v1.41 (Docker 20.x)'),
        ('1.42', 'API v1.42 (Docker 23.x)')
    ], string='API Version', default='1.41', required=True)
    
    docker_cert_path = fields.Char(string='TLS Certificates Path',
                                  help="Path to the TLS certificates directory for secure connection")
    tls_verify = fields.Boolean(string='Verify TLS', default=False,
                              help="Verify TLS certificates when connecting")
    
    # Status fields
    server_status = fields.Selection([
        ('unknown', 'Unknown'),
        ('online', 'Online'),
        ('offline', 'Offline'),
        ('error', 'Error')
    ], string='Status', default='unknown', readonly=True)
    
    docker_version = fields.Char(string='Docker Version', readonly=True)
    docker_api_info = fields.Text(string='Docker API Info', readonly=True)
    os_info = fields.Char(string='OS Info', readonly=True)
    
    cpu_usage = fields.Float(string='CPU Usage (%)', readonly=True)
    memory_usage = fields.Float(string='Memory Usage (%)', readonly=True)
    disk_usage = fields.Float(string='Disk Usage (%)', readonly=True)
    
    container_count = fields.Integer(string='Containers', compute='_compute_docker_stats', store=True)
    running_container_count = fields.Integer(string='Running', compute='_compute_docker_stats', store=True)
    image_count = fields.Integer(string='Images', compute='_compute_docker_stats', store=True)
    volume_count = fields.Integer(string='Volumes', compute='_compute_docker_stats', store=True)
    network_count = fields.Integer(string='Networks', compute='_compute_docker_stats', store=True)
    
    last_check = fields.Datetime(string='Last Check', readonly=True)
    notes = fields.Text(string='Notes')
    
    # Relationships
    container_ids = fields.One2many('docker.container', 'server_id', string='Containers')
    image_ids = fields.One2many('docker.image', 'server_id', string='Images')
    network_ids = fields.One2many('docker.network', 'server_id', string='Networks')
    volume_ids = fields.One2many('docker.volume', 'server_id', string='Volumes')
    task_ids = fields.One2many('docker.task', 'server_id', string='Tasks')
    log_ids = fields.One2many('docker.logs', 'server_id', string='Logs')
    
    # Connection settings
    timeout = fields.Integer(string='Timeout (seconds)', default=60,
                           help="Connection timeout in seconds")
    retries = fields.Integer(string='Retries', default=3,
                           help="Number of retries on connection failure")
    
    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'Server name must be unique!')
    ]
    
    # -------------------------------------------------------------------------
    # Compute and onchange methods
    # -------------------------------------------------------------------------
    @api.depends('container_ids', 'image_ids', 'volume_ids', 'network_ids')
    def _compute_docker_stats(self):
        for server in self:
            # These will be computed live when the function is called
            server.container_count = 0
            server.running_container_count = 0
            server.image_count = 0
            server.volume_count = 0
            server.network_count = 0
    
    @api.onchange('ssh_client_id')
    def _onchange_ssh_client(self):
        if self.ssh_client_id:
            self.name = self.ssh_client_id.name
    
    # -------------------------------------------------------------------------
    # CRUD methods
    # -------------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        # First create the records normally
        records = super(DockerServer, self).create(vals_list)
        
        # Schedule a check connection after the transaction is completed
        # to avoid _unknown object errors during creation
        self.env.cr.after_commit.add(lambda: self._post_creation_check(records))
        
        return records
        
    def _post_creation_check(self, records):
        """Run connection check after the record has been fully created and committed"""
        try:
            for record in records:
                if record.exists():  # Only check if the record still exists
                    record._check_connection()
        except Exception as e:
            _logger.error("Failed to run post-creation connection check: %s", str(e))
        
    def write(self, vals):
        result = super(DockerServer, self).write(vals)
        if 'ssh_client_id' in vals or 'docker_host' in vals or 'docker_api_version' in vals:
            self._check_connection()
        return result
    
    def unlink(self):
        # Log the deletion for auditing
        for server in self:
            _logger.info('Docker server %s (ID: %s) deleted by user %s (ID: %s)',
                        server.name, server.id, self.env.user.name, self.env.user.id)
        return super(DockerServer, self).unlink()
    
    # -------------------------------------------------------------------------
    # Action methods
    # -------------------------------------------------------------------------
    def action_check_connection(self):
        self.ensure_one()
        self._check_connection()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Connection Check'),
                'message': _('Connection check completed for %s') % self.name,
                'type': 'info',
                'sticky': False,
            }
        }
    
    def action_refresh_server_info(self):
        self.ensure_one()
        self._refresh_server_info()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Server Info'),
                'message': _('Server information updated for %s') % self.name,
                'type': 'info',
                'sticky': False,
            }
        }
    
    def action_scan_containers(self):
        self.ensure_one()
        self._scan_containers()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Container Scan'),
                'message': _('Container scan completed for %s') % self.name,
                'type': 'info',
                'sticky': False,
            }
        }
    
    def action_scan_images(self):
        self.ensure_one()
        self._scan_images()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Image Scan'),
                'message': _('Image scan completed for %s') % self.name,
                'type': 'info',
                'sticky': False,
            }
        }
    
    def action_scan_networks(self):
        self.ensure_one()
        self._scan_networks()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Network Scan'),
                'message': _('Network scan completed for %s') % self.name,
                'type': 'info',
                'sticky': False,
            }
        }
    
    def action_scan_volumes(self):
        self.ensure_one()
        self._scan_volumes()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Volume Scan'),
                'message': _('Volume scan completed for %s') % self.name,
                'type': 'info',
                'sticky': False,
            }
        }
    
    def action_scan_all(self):
        self.ensure_one()
        self._check_connection()
        self._refresh_server_info()
        self._scan_containers()
        self._scan_images()
        self._scan_networks()
        self._scan_volumes()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Full Scan'),
                'message': _('Full system scan completed for %s') % self.name,
                'type': 'info',
                'sticky': False,
            }
        }
    
    def action_view_containers(self):
        self.ensure_one()
        return {
            'name': _('Containers on %s') % self.name,
            'view_mode': 'tree,form',
            'res_model': 'docker.container',
            'domain': [('server_id', '=', self.id)],
            'type': 'ir.actions.act_window',
            'context': {'default_server_id': self.id},
        }
    
    def action_view_images(self):
        self.ensure_one()
        return {
            'name': _('Images on %s') % self.name,
            'view_mode': 'tree,form',
            'res_model': 'docker.image',
            'domain': [('server_id', '=', self.id)],
            'type': 'ir.actions.act_window',
            'context': {'default_server_id': self.id},
        }
    
    def action_view_networks(self):
        self.ensure_one()
        return {
            'name': _('Networks on %s') % self.name,
            'view_mode': 'tree,form',
            'res_model': 'docker.network',
            'domain': [('server_id', '=', self.id)],
            'type': 'ir.actions.act_window',
            'context': {'default_server_id': self.id},
        }
    
    def action_view_volumes(self):
        self.ensure_one()
        return {
            'name': _('Volumes on %s') % self.name,
            'view_mode': 'tree,form',
            'res_model': 'docker.volume',
            'domain': [('server_id', '=', self.id)],
            'type': 'ir.actions.act_window',
            'context': {'default_server_id': self.id},
        }
    
    def action_view_tasks(self):
        self.ensure_one()
        return {
            'name': _('Tasks on %s') % self.name,
            'view_mode': 'tree,form',
            'res_model': 'docker.task',
            'domain': [('server_id', '=', self.id)],
            'type': 'ir.actions.act_window',
            'context': {'default_server_id': self.id},
        }
    
    def action_view_logs(self):
        self.ensure_one()
        return {
            'name': _('Logs for %s') % self.name,
            'view_mode': 'tree,form',
            'res_model': 'docker.logs',
            'domain': [('server_id', '=', self.id)],
            'type': 'ir.actions.act_window',
            'context': {'default_server_id': self.id},
        }
    
    def action_execute_command(self):
        self.ensure_one()
        return {
            'name': _('Execute Docker Command'),
            'type': 'ir.actions.act_window',
            'res_model': 'docker.command.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_server_id': self.id},
        }
    
    # -------------------------------------------------------------------------
    # Helper methods for server interaction
    # -------------------------------------------------------------------------
    def _check_connection(self):
        self.ensure_one()
        
        if not self.ssh_client_id:
            self.server_status = 'error'
            self._create_log_entry('error', 'No SSH client configured')
            return False
        
        try:
            # First check SSH connection
            ssh_client = self.ssh_client_id
            ssh_result = ssh_client.test_connection()
            
            if "Connection test failed" in ssh_result:
                self.server_status = 'offline'
                self._create_log_entry('error', 'SSH connection failed')
                return False
                
            # Now check Docker connection
            cmd = "docker info --format '{{json .}}'"
            result = ssh_client.exec_command(cmd)
            
            # Look for JSON output in the result
            json_match = re.search(r'({.*})', result, re.DOTALL)
            if not json_match:
                self.server_status = 'error'
                self._create_log_entry('error', f'Docker connection failed, invalid response: {result}')
                return False
                
            try:
                docker_info = json.loads(json_match.group(1))
                self.docker_version = docker_info.get('ServerVersion', 'Unknown')
                self.server_status = 'online'
                self.last_check = fields.Datetime.now()
                self._create_log_entry('info', 'Connection successful')
                return True
            except json.JSONDecodeError:
                self.server_status = 'error'
                self._create_log_entry('error', f'Failed to parse Docker info: {result}')
                return False
                
        except Exception as e:
            self.server_status = 'error'
            self._create_log_entry('error', f'Connection check failed: {str(e)}')
            return False
    
    def _refresh_server_info(self):
        self.ensure_one()
        
        if not self._check_connection():
            return False
            
        try:
            ssh_client = self.ssh_client_id
            
            # Get Docker info
            cmd = "docker info --format '{{json .}}'"
            result = ssh_client.exec_command(cmd)
            
            json_match = re.search(r'({.*})', result, re.DOTALL)
            if json_match:
                docker_info = json.loads(json_match.group(1))
                self.docker_api_info = json.dumps(docker_info, indent=2)
                self.os_info = f"{docker_info.get('OperatingSystem', 'Unknown')} ({docker_info.get('KernelVersion', 'Unknown')})"
                
            # Get system resource usage
            cmd = "top -bn1 | grep 'Cpu(s)' | awk '{print $2}' && free -m | grep Mem | awk '{print $3/$2 * 100}' && df -h / | grep / | awk '{print $5}' | tr -d '%'"
            result = ssh_client.exec_command(cmd)
            
            lines = result.strip().split('\n')
            if len(lines) >= 3:
                try:
                    self.cpu_usage = float(lines[0])
                    self.memory_usage = float(lines[1])
                    self.disk_usage = float(lines[2])
                except (ValueError, IndexError):
                    _logger.warning("Could not parse resource usage information")
            
            # Get container counts
            cmd = "docker ps -q | wc -l && docker ps -qa | wc -l && docker images -q | wc -l && docker volume ls -q | wc -l && docker network ls -q | wc -l"
            result = ssh_client.exec_command(cmd)
            
            lines = result.strip().split('\n')
            if len(lines) >= 5:
                try:
                    self.running_container_count = int(lines[0])
                    self.container_count = int(lines[1])
                    self.image_count = int(lines[2])
                    self.volume_count = int(lines[3])
                    self.network_count = int(lines[4])
                except (ValueError, IndexError):
                    _logger.warning("Could not parse Docker resource counts")
            
            self.last_check = fields.Datetime.now()
            self._create_log_entry('info', 'Server information refreshed')
            return True
            
        except Exception as e:
            self._create_log_entry('error', f'Failed to refresh server info: {str(e)}')
            return False
    
    def _scan_containers(self):
        """Scan and update containers on the server"""
        self.ensure_one()
        
        if not self._check_connection():
            return False
            
        try:
            ssh_client = self.ssh_client_id
            
            # Get container list in JSON format
            cmd = "docker ps -a --format '{{json .}}'"
            result = ssh_client.exec_command(cmd)
            
            # Process each line as a JSON object
            container_ids = []
            for line in result.strip().split('\n'):
                if not line:
                    continue
                    
                try:
                    container_data = json.loads(line)
                    container_id = container_data.get('ID')
                    if not container_id:
                        continue
                        
                    # Check if container already exists
                    container = self.env['docker.container'].search([
                        ('docker_id', '=', container_id),
                        ('server_id', '=', self.id)
                    ], limit=1)
                    
                    container_name = container_data.get('Names', '').strip('/')
                    image_name = container_data.get('Image', '')
                    status = container_data.get('Status', '')
                    ports = container_data.get('Ports', '')
                    
                    if container:
                        # Update existing container
                        container.write({
                            'name': container_name,
                            'image': image_name,
                            'status': self._parse_container_status(status),
                            'status_text': status,
                            'ports': ports,
                            'last_updated': fields.Datetime.now(),
                        })
                    else:
                        # Create new container
                        container = self.env['docker.container'].create({
                            'name': container_name,
                            'docker_id': container_id,
                            'server_id': self.id,
                            'image': image_name,
                            'status': self._parse_container_status(status),
                            'status_text': status,
                            'ports': ports,
                            'last_updated': fields.Datetime.now(),
                        })
                    
                    container_ids.append(container.id)
                    
                except json.JSONDecodeError:
                    _logger.warning(f"Could not parse container JSON: {line}")
                except Exception as e:
                    _logger.error(f"Error processing container: {str(e)}")
            
            # Mark containers not found as inactive
            orphaned_containers = self.env['docker.container'].search([
                ('server_id', '=', self.id),
                ('id', 'not in', container_ids),
                ('active', '=', True),
            ])
            
            if orphaned_containers:
                orphaned_containers.write({'active': False})
            
            self._create_log_entry('info', f'Container scan complete, found {len(container_ids)} containers')
            return True
            
        except Exception as e:
            self._create_log_entry('error', f'Failed to scan containers: {str(e)}')
            return False
    
    def _scan_images(self):
        """Scan and update images on the server"""
        self.ensure_one()
        
        if not self._check_connection():
            return False
            
        try:
            ssh_client = self.ssh_client_id
            
            # Get image list in JSON format
            cmd = "docker images --format '{{json .}}'"
            result = ssh_client.exec_command(cmd)
            
            # Process each line as a JSON object
            image_ids = []
            for line in result.strip().split('\n'):
                if not line:
                    continue
                    
                try:
                    image_data = json.loads(line)
                    repository = image_data.get('Repository', '')
                    tag = image_data.get('Tag', '')
                    image_id = image_data.get('ID', '')
                    
                    if not image_id:
                        continue
                        
                    # Create a unique key for the image
                    name = f"{repository}:{tag}" if tag and tag != '<none>' else repository
                    
                    # Check if image already exists
                    image = self.env['docker.image'].search([
                        ('docker_id', '=', image_id),
                        ('server_id', '=', self.id)
                    ], limit=1)
                    
                    size = image_data.get('Size', '0')
                    created = image_data.get('CreatedAt', '')
                    
                    if image:
                        # Update existing image
                        image.write({
                            'name': name,
                            'repository': repository,
                            'tag': tag,
                            'size': size,
                            'created_at': created,
                            'last_updated': fields.Datetime.now(),
                        })
                    else:
                        # Create new image
                        image = self.env['docker.image'].create({
                            'name': name,
                            'docker_id': image_id,
                            'server_id': self.id,
                            'repository': repository,
                            'tag': tag,
                            'size': size,
                            'created_at': created,
                            'last_updated': fields.Datetime.now(),
                        })
                    
                    image_ids.append(image.id)
                    
                except json.JSONDecodeError:
                    _logger.warning(f"Could not parse image JSON: {line}")
                except Exception as e:
                    _logger.error(f"Error processing image: {str(e)}")
            
            # Mark images not found as inactive
            orphaned_images = self.env['docker.image'].search([
                ('server_id', '=', self.id),
                ('id', 'not in', image_ids),
                ('active', '=', True),
            ])
            
            if orphaned_images:
                orphaned_images.write({'active': False})
            
            self._create_log_entry('info', f'Image scan complete, found {len(image_ids)} images')
            return True
            
        except Exception as e:
            self._create_log_entry('error', f'Failed to scan images: {str(e)}')
            return False
    
    def _scan_networks(self):
        """Scan and update networks on the server"""
        self.ensure_one()
        
        if not self._check_connection():
            return False
            
        try:
            ssh_client = self.ssh_client_id
            
            # Get network list in JSON format
            cmd = "docker network ls --format '{{json .}}'"
            result = ssh_client.exec_command(cmd)
            
            # Process each line as a JSON object
            network_ids = []
            for line in result.strip().split('\n'):
                if not line:
                    continue
                    
                try:
                    network_data = json.loads(line)
                    network_id = network_data.get('ID', '')
                    
                    if not network_id:
                        continue
                        
                    # Check if network already exists
                    network = self.env['docker.network'].search([
                        ('docker_id', '=', network_id),
                        ('server_id', '=', self.id)
                    ], limit=1)
                    
                    name = network_data.get('Name', '')
                    driver = network_data.get('Driver', '')
                    scope = network_data.get('Scope', '')
                    
                    if network:
                        # Update existing network
                        network.write({
                            'name': name,
                            'driver': driver,
                            'scope': scope,
                            'last_updated': fields.Datetime.now(),
                        })
                    else:
                        # Create new network
                        network = self.env['docker.network'].create({
                            'name': name,
                            'docker_id': network_id,
                            'server_id': self.id,
                            'driver': driver,
                            'scope': scope,
                            'last_updated': fields.Datetime.now(),
                        })
                    
                    # Get additional network details
                    cmd = f"docker network inspect {network_id} --format '{{{{json .}}}}'"
                    detail_result = ssh_client.exec_command(cmd)
                    
                    try:
                        if detail_result and '{' in detail_result:
                            network_details = json.loads(detail_result)
                            if isinstance(network_details, list) and network_details:
                                network_detail = network_details[0]
                                
                                # Extract IPAM config
                                ipam_config = network_detail.get('IPAM', {}).get('Config', [])
                                if ipam_config and isinstance(ipam_config, list):
                                    subnet = ipam_config[0].get('Subnet', '')
                                    gateway = ipam_config[0].get('Gateway', '')
                                    
                                    network.write({
                                        'subnet': subnet,
                                        'gateway': gateway,
                                    })
                    except Exception as detail_err:
                        _logger.warning(f"Error fetching network details: {str(detail_err)}")
                    
                    network_ids.append(network.id)
                    
                except json.JSONDecodeError:
                    _logger.warning(f"Could not parse network JSON: {line}")
                except Exception as e:
                    _logger.error(f"Error processing network: {str(e)}")
            
            # Mark networks not found as inactive
            orphaned_networks = self.env['docker.network'].search([
                ('server_id', '=', self.id),
                ('id', 'not in', network_ids),
                ('active', '=', True),
            ])
            
            if orphaned_networks:
                orphaned_networks.write({'active': False})
            
            self._create_log_entry('info', f'Network scan complete, found {len(network_ids)} networks')
            return True
            
        except Exception as e:
            self._create_log_entry('error', f'Failed to scan networks: {str(e)}')
            return False
    
    def _scan_volumes(self):
        """Scan and update volumes on the server"""
        self.ensure_one()
        
        if not self._check_connection():
            return False
            
        try:
            ssh_client = self.ssh_client_id
            
            # Get volume list in JSON format
            cmd = "docker volume ls --format '{{json .}}'"
            result = ssh_client.exec_command(cmd)
            
            # Process each line as a JSON object
            volume_ids = []
            for line in result.strip().split('\n'):
                if not line:
                    continue
                    
                try:
                    volume_data = json.loads(line)
                    name = volume_data.get('Name', '')
                    
                    if not name:
                        continue
                        
                    # Check if volume already exists
                    volume = self.env['docker.volume'].search([
                        ('name', '=', name),
                        ('server_id', '=', self.id)
                    ], limit=1)
                    
                    driver = volume_data.get('Driver', '')
                    
                    if volume:
                        # Update existing volume
                        volume.write({
                            'driver': driver,
                            'last_updated': fields.Datetime.now(),
                        })
                    else:
                        # Create new volume
                        volume = self.env['docker.volume'].create({
                            'name': name,
                            'server_id': self.id,
                            'driver': driver,
                            'last_updated': fields.Datetime.now(),
                        })
                    
                    # Get additional volume details
                    cmd = f"docker volume inspect {name} --format '{{{{json .}}}}'"
                    detail_result = ssh_client.exec_command(cmd)
                    
                    try:
                        if detail_result and '{' in detail_result:
                            volume_details = json.loads(detail_result)
                            if isinstance(volume_details, list) and volume_details:
                                volume_detail = volume_details[0]
                                
                                # Extract mountpoint
                                mountpoint = volume_detail.get('Mountpoint', '')
                                
                                volume.write({
                                    'mountpoint': mountpoint,
                                })
                    except Exception as detail_err:
                        _logger.warning(f"Error fetching volume details: {str(detail_err)}")
                    
                    volume_ids.append(volume.id)
                    
                except json.JSONDecodeError:
                    _logger.warning(f"Could not parse volume JSON: {line}")
                except Exception as e:
                    _logger.error(f"Error processing volume: {str(e)}")
            
            # Mark volumes not found as inactive
            orphaned_volumes = self.env['docker.volume'].search([
                ('server_id', '=', self.id),
                ('id', 'not in', volume_ids),
                ('active', '=', True),
            ])
            
            if orphaned_volumes:
                orphaned_volumes.write({'active': False})
            
            self._create_log_entry('info', f'Volume scan complete, found {len(volume_ids)} volumes')
            return True
            
        except Exception as e:
            self._create_log_entry('error', f'Failed to scan volumes: {str(e)}')
            return False
    
    def _create_log_entry(self, level, message):
        """Create a log entry for the server"""
        self.ensure_one()
        
        # Only create log entries if the record has an ID (has been saved to DB)
        if not self.id:
            _logger.info("Cannot create log entry for unsaved record: %s - %s", level, message)
            return
            
        try:
            self.env['docker.logs'].create({
                'server_id': self.id,
                'level': level,
                'name': message,
                'user_id': self.env.user.id,
            })
        except Exception as e:
            _logger.error("Failed to create log entry: %s", str(e))
    
    def _parse_container_status(self, status_text):
        """Parse the container status text and return a status code"""
        if not status_text:
            return 'unknown'
            
        status_lower = status_text.lower()
        
        if 'running' in status_lower:
            return 'running'
        elif 'created' in status_lower:
            return 'created'
        elif 'exited' in status_lower:
            return 'exited'
        elif 'paused' in status_lower:
            return 'paused'
        elif 'restarting' in status_lower:
            return 'restarting'
        elif 'dead' in status_lower:
            return 'dead'
        else:
            return 'unknown'
    
    # -------------------------------------------------------------------------
    # Cron methods
    # -------------------------------------------------------------------------
    @api.model
    def _cron_refresh_servers(self):
        """Refresh all active server statuses
        Called by scheduled action
        """
        servers = self.search([('active', '=', True)])
        for server in servers:
            try:
                server._check_connection()
                server._refresh_server_info()
                _logger.info(f"Refreshed server info for {server.name}")
            except Exception as e:
                _logger.error(f"Error refreshing server {server.name}: {str(e)}")
    
    @api.model
    def _cron_auto_prune(self):
        """Auto-prune dangling images on all active servers
        Called by scheduled action (disabled by default)
        """
        servers = self.search([('active', '=', True)])
        for server in servers:
            try:
                if not server._check_connection():
                    continue
                
                ssh_client = server.ssh_client_id
                if not ssh_client:
                    continue
                
                # Run docker system prune for unused images
                cmd = "docker system prune -f --filter 'until=24h'"
                result = ssh_client.exec_command(cmd)
                
                # Log the result
                server._create_log_entry('info', f'Auto-pruned dangling images: {result}')
                _logger.info(f"Auto-pruned dangling images on {server.name}")
            except Exception as e:
                _logger.error(f"Error auto-pruning images on server {server.name}: {str(e)}")