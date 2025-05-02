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
    
    is_custom = fields.Boolean('Custom Template', default=False, help="Used to identify standard templates")
    
    title = fields.Char('Title', required=True)
    description = fields.Text('Description')
    template_type = fields.Selection([
        ('1', 'Standalone / Podman'),
        ('2', 'Swarm')
    ], string='Type', default='1', required=True)
    platform = fields.Selection([
        ('linux', 'Linux'),
        ('windows', 'Windows')
    ], string='Platform', default='linux', required=True)
    template_id = fields.Integer('Template ID')
    server_id = fields.Many2one('j_portainer.server', string='Server', required=True, ondelete='cascade')
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
    
    @api.depends('categories')
    def _compute_category_ids(self):
        """Compute and maintain category_ids from categories text"""
        category_model = self.env['j_portainer.template.category']
        
        for template in self:
            category_list = []
            
            if template.categories:
                try:
                    # Try to parse as JSON
                    categories = json.loads(template.categories)
                    if isinstance(categories, list):
                        for category in categories:
                            if isinstance(category, str):
                                # Get or create the category
                                category_obj = category_model.search([('name', '=', category)], limit=1)
                                if not category_obj:
                                    category_obj = category_model.create({'name': category})
                                category_list.append(category_obj.id)
                            elif isinstance(category, dict) and 'name' in category:
                                # Handle object format with name key
                                category_obj = category_model.search([('name', '=', category['name'])], limit=1)
                                if not category_obj:
                                    category_obj = category_model.create({'name': category['name']})
                                category_list.append(category_obj.id)
                except Exception as e:
                    _logger.warning(f"Error parsing categories: {str(e)}")
                    # Try to parse as comma-separated string
                    try:
                        for category in template.categories.split(','):
                            category = category.strip()
                            if category:
                                category_obj = category_model.search([('name', '=', category)], limit=1)
                                if not category_obj:
                                    category_obj = category_model.create({'name': category})
                                category_list.append(category_obj.id)
                    except Exception as e2:
                        _logger.error(f"Failed to parse categories as string: {str(e2)}")
            
            template.category_ids = [(6, 0, category_list)]
    
    @api.depends('environment_variables')
    def _compute_formatted_env(self):
        """Format environment variables for display"""
        for template in self:
            result = ""
            
            if template.environment_variables:
                try:
                    env_vars = json.loads(template.environment_variables)
                    if isinstance(env_vars, list):
                        for env in env_vars:
                            if isinstance(env, dict):
                                name = env.get('name', '')
                                default_value = env.get('default', '')
                                description = env.get('description', '')
                                label = env.get('label', '')
                                
                                result += f"{name}: {default_value}\n"
                                if description:
                                    result += f"  Description: {description}\n"
                                if label:
                                    result += f"  Label: {label}\n"
                                result += "\n"
                            elif isinstance(env, str):
                                result += f"{env}\n"
                except Exception as e:
                    result = f"Error parsing environment variables: {str(e)}"
            
            template.get_formatted_env = result
    
    @api.depends('volumes')
    def _compute_formatted_volumes(self):
        """Format volumes for display"""
        for template in self:
            result = ""
            
            if template.volumes:
                try:
                    volumes = json.loads(template.volumes)
                    if isinstance(volumes, list):
                        for volume in volumes:
                            if isinstance(volume, dict):
                                container = volume.get('container', '')
                                bind = volume.get('bind', '')
                                result += f"Container: {container}\n"
                                result += f"  Bind: {bind}\n\n"
                            elif isinstance(volume, str):
                                result += f"{volume}\n"
                except Exception as e:
                    result = f"Error parsing volumes: {str(e)}"
            
            template.get_formatted_volumes = result
    
    @api.depends('ports')
    def _compute_formatted_ports(self):
        """Format ports for display"""
        for template in self:
            result = ""
            
            if template.ports:
                try:
                    ports = json.loads(template.ports)
                    if isinstance(ports, list):
                        for port in ports:
                            if isinstance(port, dict):
                                container = port.get('container', '')
                                host = port.get('host', '')
                                protocol = port.get('protocol', 'tcp')
                                result += f"Container: {container}\n"
                                result += f"  Host: {host}\n"
                                result += f"  Protocol: {protocol}\n\n"
                            elif isinstance(port, str):
                                result += f"{port}\n"
                except Exception as e:
                    result = f"Error parsing ports: {str(e)}"
            
            template.get_formatted_ports = result
    
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