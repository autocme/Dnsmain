# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class SshSavedCommand(models.Model):
    _name = 'ssh.saved.command'
    _description = 'SSH Saved Command'
    _order = 'name'

    name = fields.Char(string='Command Name', required=True, index=True, 
                      help='A descriptive name for this saved command')
    command = fields.Text(string='Command', required=True, 
                        help='The command to execute on the server')
    description = fields.Text(string='Description', 
                            help='Optional description of what this command does')
    
    ssh_client_id = fields.Many2one('ssh.client', string='SSH Client', 
                                  ondelete='cascade',
                                  help='The SSH client this command belongs to')
    
    color = fields.Integer(string='Color Index')
    sequence = fields.Integer(string='Sequence', default=10)
    is_favorite = fields.Boolean(string='Favorite', default=False,
                               help='Mark as favorite for quick access')
    
    last_used = fields.Datetime(string='Last Used', readonly=True)
    use_count = fields.Integer(string='Use Count', default=0, readonly=True,
                             help='Number of times this command has been used')
    
    category = fields.Selection([
        ('system', 'System Administration'),
        ('network', 'Network'),
        ('file', 'File Operations'),
        ('database', 'Database'),
        ('monitoring', 'Monitoring'),
        ('custom', 'Custom'),
    ], string='Category', default='custom')
    
    tag_ids = fields.Many2many('ssh.command.tag', string='Tags')
    
    @api.constrains('command')
    def _check_command(self):
        for record in self:
            if not record.command or not record.command.strip():
                raise ValidationError(_('Command cannot be empty'))
    
    def execute_command(self):
        """Execute this saved command on the associated SSH client"""
        self.ensure_one()
        if not self.ssh_client_id:
            raise ValidationError(_('No SSH client associated with this command'))
        
        # Update usage statistics
        self.write({
            'last_used': fields.Datetime.now(),
            'use_count': self.use_count + 1,
        })
        
        # Execute the command on the SSH client
        return self.ssh_client_id.exec_command(self.command)

class SshCommandTag(models.Model):
    _name = 'ssh.command.tag'
    _description = 'SSH Command Tag'
    
    name = fields.Char(string='Tag Name', required=True, index=True)
    color = fields.Integer(string='Color Index')