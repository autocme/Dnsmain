import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)

class DockerLogs(models.Model):
    _name = 'docker.logs'
    _description = 'Docker Logs'
    _order = 'create_date desc'
    
    name = fields.Char(string='Message', required=True, 
                     help="Log message")
    
    level = fields.Selection([
        ('debug', 'Debug'),
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('error', 'Error')
    ], string='Level', required=True, default='info')
    
    # Related entities
    server_id = fields.Many2one('docker.server', string='Server',
                              ondelete='cascade',
                              help="Server related to this log")
    
    container_id = fields.Many2one('docker.container', string='Container',
                                 ondelete='cascade',
                                 help="Container related to this log")
    
    image_id = fields.Many2one('docker.image', string='Image',
                             ondelete='cascade',
                             help="Image related to this log")
    
    network_id = fields.Many2one('docker.network', string='Network',
                               ondelete='cascade',
                               help="Network related to this log")
    
    volume_id = fields.Many2one('docker.volume', string='Volume',
                              ondelete='cascade',
                              help="Volume related to this log")
    
    task_id = fields.Many2one('docker.task', string='Task',
                            ondelete='cascade',
                            help="Task related to this log")
    
    user_id = fields.Many2one('res.users', string='User',
                            default=lambda self: self.env.user.id,
                            help="User who performed the action")
    
    details = fields.Text(string='Details', 
                        help="Additional details about the log entry")
    
    # -------------------------------------------------------------------------
    # Color-coding methods
    # -------------------------------------------------------------------------
    def get_level_color(self):
        """Return a color code for the log level"""
        colors = {
            'debug': '#6c757d',  # gray
            'info': '#17a2b8',   # info blue
            'warning': '#ffc107', # warning yellow
            'error': '#dc3545'    # danger red
        }
        return colors.get(self.level, '#6c757d')
    
    # -------------------------------------------------------------------------
    # Static methods
    # -------------------------------------------------------------------------
    @api.model
    def log(self, level, message, server_id=None, container_id=None, 
            image_id=None, network_id=None, volume_id=None, task_id=None, 
            details=None):
        """Create a log entry programmatically"""
        vals = {
            'name': message,
            'level': level,
            'details': details,
            'user_id': self.env.user.id,
        }
        
        if server_id:
            vals['server_id'] = server_id
        if container_id:
            vals['container_id'] = container_id
        if image_id:
            vals['image_id'] = image_id
        if network_id:
            vals['network_id'] = network_id
        if volume_id:
            vals['volume_id'] = volume_id
        if task_id:
            vals['task_id'] = task_id
            
        return self.create(vals)
    
    # -------------------------------------------------------------------------
    # Action methods
    # -------------------------------------------------------------------------
    def action_view_related_entity(self):
        """Open the related entity of this log entry"""
        self.ensure_one()
        
        if self.container_id:
            return {
                'name': _('Container'),
                'view_mode': 'form',
                'res_model': 'docker.container',
                'res_id': self.container_id.id,
                'type': 'ir.actions.act_window',
            }
        elif self.image_id:
            return {
                'name': _('Image'),
                'view_mode': 'form',
                'res_model': 'docker.image',
                'res_id': self.image_id.id,
                'type': 'ir.actions.act_window',
            }
        elif self.network_id:
            return {
                'name': _('Network'),
                'view_mode': 'form',
                'res_model': 'docker.network',
                'res_id': self.network_id.id,
                'type': 'ir.actions.act_window',
            }
        elif self.volume_id:
            return {
                'name': _('Volume'),
                'view_mode': 'form',
                'res_model': 'docker.volume',
                'res_id': self.volume_id.id,
                'type': 'ir.actions.act_window',
            }
        elif self.task_id:
            return {
                'name': _('Task'),
                'view_mode': 'form',
                'res_model': 'docker.task',
                'res_id': self.task_id.id,
                'type': 'ir.actions.act_window',
            }
        elif self.server_id:
            return {
                'name': _('Server'),
                'view_mode': 'form',
                'res_model': 'docker.server',
                'res_id': self.server_id.id,
                'type': 'ir.actions.act_window',
            }
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Error'),
                'message': _('No related entity found for this log.'),
                'type': 'warning',
                'sticky': False,
            }
        }