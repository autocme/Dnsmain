import json
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

class DockerVolume(models.Model):
    _name = 'docker.volume'
    _description = 'Docker Volume'
    _order = 'name'
    _inherit = ['safe.read.mixin']
    # Commenting out mail inheritance until mail module is properly loaded
    # _inherit = ['mail.thread', 'mail.activity.mixin', 'safe.read.mixin']

    name = fields.Char(string='Name', required=True,
                     help="Name of the Docker volume")
    
    server_id = fields.Many2one('docker.server', string='Server', required=True,
                              ondelete='cascade',
                              help="Server where this volume exists")
    
    active = fields.Boolean(default=True)
    
    # Volume details
    driver = fields.Char(string='Driver', readonly=True,
                       help="Volume driver (local, nfs, etc.)")
    
    mountpoint = fields.Char(string='Mountpoint', readonly=True,
                           help="Location on disk where the volume is stored")
    
    scope = fields.Char(string='Scope', readonly=True,
                      help="Volume scope (local, global)")
    
    # Usage information
    used_by_containers = fields.Text(string='Used By Containers', readonly=True)
    
    used_by_container_count = fields.Integer(string='Used By Containers', 
                                           compute='_compute_used_by_containers',
                                           store=True)
    
    size = fields.Char(string='Size', readonly=True,
                     help="Size of the volume (if available)")
    
    # Additional information
    labels = fields.Text(string='Labels', readonly=True)
    
    options = fields.Text(string='Options', readonly=True,
                        help="Volume creation options")
    
    last_updated = fields.Datetime(string='Last Updated', readonly=True)
    notes = fields.Text(string='Notes')
    
    # Related logs
    log_ids = fields.One2many('docker.logs', 'volume_id', string='Logs')
    
    # -------------------------------------------------------------------------
    # Compute methods
    # -------------------------------------------------------------------------
    @api.depends('used_by_containers')
    def _compute_used_by_containers(self):
        for volume in self:
            count = 0
            if volume.used_by_containers:
                count = len(volume.used_by_containers.split('\n'))
            volume.used_by_container_count = count
    
    # -------------------------------------------------------------------------
    # Action methods
    # -------------------------------------------------------------------------
    def action_refresh(self):
        """Refresh volume details"""
        self.ensure_one()
        self._update_volume_details()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Volume Refresh'),
                'message': _('Volume details updated for %s') % self.name,
                'type': 'info',
                'sticky': False,
            }
        }
    
    def action_remove(self):
        """Remove the volume"""
        self.ensure_one()
        
        if self.used_by_container_count > 0:
            raise UserError(_('Cannot remove volume that is being used by containers.'))
        
        try:
            server = self.server_id
            ssh_client = server.ssh_client_id
            
            if not ssh_client:
                raise UserError(_('No SSH client configured for server %s') % server.name)
            
            cmd = f"docker volume rm {self.name}"
            result = ssh_client.exec_command(cmd)
            
            if self.name in result:
                self.active = False
                self.last_updated = fields.Datetime.now()
                self._create_log_entry('info', 'Volume removed')
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Volume Removed'),
                        'message': _('Volume %s removed successfully') % self.name,
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                self._create_log_entry('error', f'Failed to remove volume: {result}')
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Error'),
                        'message': _('Failed to remove volume. See logs for details.'),
                        'type': 'warning',
                        'sticky': False,
                    }
                }
                
        except Exception as e:
            self._create_log_entry('error', f'Error removing volume: {str(e)}')
            raise UserError(_('Error removing volume: %s') % str(e))
    
    def action_inspect(self):
        """Inspect volume details"""
        self.ensure_one()
        try:
            server = self.server_id
            ssh_client = server.ssh_client_id
            
            if not ssh_client:
                raise UserError(_('No SSH client configured for server %s') % server.name)
            
            cmd = f"docker volume inspect {self.name}"
            result = ssh_client.exec_command(cmd)
            
            return {
                'name': _('Volume Inspection'),
                'type': 'ir.actions.act_window',
                'res_model': 'docker.inspect.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_volume_id': self.id,
                    'default_inspect_content': result
                },
            }
                
        except Exception as e:
            self._create_log_entry('error', f'Error inspecting volume: {str(e)}')
            raise UserError(_('Error inspecting volume: %s') % str(e))
    
    def action_create_container(self):
        """Open wizard to create a container using this volume"""
        self.ensure_one()
        return {
            'name': _('Create Container with Volume'),
            'type': 'ir.actions.act_window',
            'res_model': 'docker.create.container.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_server_id': self.server_id.id,
                'default_volume_id': self.id,
                'default_volume_name': self.name
            },
        }
    
    def action_create_volume(self):
        """Open wizard to create a new volume"""
        self.ensure_one()
        return {
            'name': _('Create Volume'),
            'type': 'ir.actions.act_window',
            'res_model': 'docker.create.volume.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_server_id': self.server_id.id,
            },
        }
    
    def action_browse_volume(self):
        """Browse the volume contents (if supported by server)"""
        self.ensure_one()
        try:
            server = self.server_id
            ssh_client = server.ssh_client_id
            
            if not ssh_client:
                raise UserError(_('No SSH client configured for server %s') % server.name)
            
            # First check if the mountpoint is accessible
            if not self.mountpoint:
                self._update_volume_details()
                if not self.mountpoint:
                    raise UserError(_('Could not determine volume mountpoint.'))
            
            # Try to list the contents of the volume
            cmd = f"ls -la {self.mountpoint}"
            result = ssh_client.exec_command(cmd)
            
            return {
                'name': _('Volume Contents'),
                'type': 'ir.actions.act_window',
                'res_model': 'docker.volume.browse.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_volume_id': self.id,
                    'default_content': result,
                    'default_path': self.mountpoint
                },
            }
                
        except Exception as e:
            self._create_log_entry('error', f'Error browsing volume: {str(e)}')
            raise UserError(_('Error browsing volume contents: %s') % str(e))
    
    # -------------------------------------------------------------------------
    # Helper methods for volume interaction
    # -------------------------------------------------------------------------
    def _update_volume_details(self):
        """Update volume details from Docker"""
        self.ensure_one()
        
        try:
            server = self.server_id
            ssh_client = server.ssh_client_id
            
            if not ssh_client:
                return False
            
            # Get volume details
            cmd = f"docker volume inspect {self.name} --format '{{{{json .}}}}'"
            result = ssh_client.exec_command(cmd)
            
            try:
                if result and '{' in result:
                    volume_details = json.loads(result)
                    
                    if isinstance(volume_details, list) and volume_details:
                        details = volume_details[0]
                        
                        # Extract volume basic info
                        self.driver = details.get('Driver', '')
                        self.mountpoint = details.get('Mountpoint', '')
                        self.scope = details.get('Scope', '')
                        
                        # Extract options
                        options = details.get('Options', {})
                        if options:
                            options_info = []
                            for key, value in options.items():
                                options_info.append(f"{key}={value}")
                            
                            if options_info:
                                self.options = '\n'.join(options_info)
                        
                        # Extract labels
                        labels = details.get('Labels', {})
                        if labels:
                            labels_info = []
                            for key, value in labels.items():
                                labels_info.append(f"{key}={value}")
                            
                            if labels_info:
                                self.labels = '\n'.join(labels_info)
                        
                        # Get containers using this volume
                        self._update_volume_usage()
                        
                        self.last_updated = fields.Datetime.now()
                        self._create_log_entry('info', 'Volume details updated')
                        return True
                        
            except json.JSONDecodeError as json_err:
                self._create_log_entry('error', f'Error parsing volume details: {str(json_err)}')
            except Exception as e:
                self._create_log_entry('error', f'Error updating volume details: {str(e)}')
            
            return False
                
        except Exception as e:
            self._create_log_entry('error', f'Error fetching volume details: {str(e)}')
            return False
    
    def _update_volume_usage(self):
        """Update which containers are using this volume"""
        self.ensure_one()
        
        try:
            server = self.server_id
            ssh_client = server.ssh_client_id
            
            if not ssh_client:
                return False
            
            # Find containers that use this volume
            cmd = f"docker ps -a --filter volume={self.name} --format '{{{{.Names}}}} ({{{{.ID}}}}): {{{{.Status}}}}'"
            result = ssh_client.exec_command(cmd)
            
            if result.strip():
                self.used_by_containers = result.strip()
            else:
                self.used_by_containers = False
                
            return True
                
        except Exception as e:
            _logger.error(f"Error updating volume usage: {str(e)}")
            return False
    
    def _create_log_entry(self, level, message):
        """Create a log entry for the volume"""
        self.ensure_one()
        
        self.env['docker.logs'].create({
            'server_id': self.server_id.id,
            'volume_id': self.id,
            'level': level,
            'name': message,
            'user_id': self.env.user.id,
        })