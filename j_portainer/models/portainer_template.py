#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import json
import logging

_logger = logging.getLogger(__name__)

class PortainerTemplate(models.Model):
    _name = 'j_portainer.template'
    _description = 'Portainer Template'
    _order = 'title'
    _inherit = ['j_portainer.template.mixin']
    
    is_custom = fields.Boolean('Custom Template', default=False, help="Used to identify standard templates")
    
    title = fields.Char('Title', required=True)
    description = fields.Text('Description')
    template_type = fields.Selection([
        ('1', 'Standalone / Podman'),
        ('2', 'Swarm'),
        ('3', 'Compose stack'),
    ], string='Type', default='1', required=True)
    platform = fields.Selection([
        ('linux', 'Linux'),
        ('windows', 'Windows')
    ], string='Platform', default='linux', required=True)
    template_id = fields.Integer('Template ID')
    server_id = fields.Many2one('j_portainer.server', string='Server', required=True, ondelete='cascade')
    last_sync = fields.Datetime('Last Synchronized', readonly=True)
    logo = fields.Char('Logo URL')
    registry = fields.Char('Registry')
    image = fields.Char('Image')
    repository = fields.Text('Repository')
    categories = fields.Char('Categories')  # Store raw categories string
    category_ids = fields.Many2many('j_portainer.template.category', string='Categories Tags', compute='_compute_category_ids', store=True)
    environment_variables = fields.Text('Environment Variables')
    volumes = fields.Text('Volumes')
    ports = fields.Text('Ports')
    note = fields.Text('Note')
    details = fields.Text('Details', help="Additional details about the template")
    skip_portainer_create = fields.Boolean('Skip Portainer Creation', default=False, 
                                          help='Used during sync to skip creating the template in Portainer')
    
    # Useful computed fields for display
    get_formatted_env = fields.Text('Formatted Environment Variables', compute='_compute_formatted_env')
    get_formatted_volumes = fields.Text('Formatted Volumes', compute='_compute_formatted_volumes')
    get_formatted_ports = fields.Text('Formatted Ports', compute='_compute_formatted_ports')
    # The formatting functions for environment variables, volumes, ports, and
    # categories are now inherited from j_portainer.template.mixin
    
    def action_refresh(self):
        """Refresh templates from Portainer"""
        for template in self:
            if template.server_id:
                template.server_id.sync_standard_templates()
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Templates Refreshed'),
                        'message': _("Templates have been refreshed from Portainer"),
                        'sticky': False,
                    }
                }
        
        raise UserError(_("No server found to refresh templates"))
        
    def action_deploy(self):
        """Open the deploy wizard for this template"""
        self.ensure_one()
        
        # Check that the server is connected
        if self.server_id.status != 'connected':
            raise UserError(_("Cannot deploy template: Server is not connected"))
            
        # Open the deployment wizard
        return {
            'name': _('Deploy Template'),
            'type': 'ir.actions.act_window',
            'res_model': 'j_portainer.template.deploy.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_server_id': self.server_id.id,
                'default_template_id': self.id,
                'default_is_custom': False,
                'default_template_title': self.title,
                'default_template_type': self.template_type,
                'default_name': self.title,
            }
        }