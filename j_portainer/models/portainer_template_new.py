#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import json
import logging

_logger = logging.getLogger(__name__)

class PortainerTemplateNew(models.Model):
    _name = 'j_portainer.template'
    _description = 'Portainer Template'
    _order = 'title'
    
    title = fields.Char('Title', required=True)
    description = fields.Text('Description')
    template_type = fields.Selection([
        (1, 'Container'),
        (2, 'Stack'),
        (3, 'App Template')
    ], string='Type', default=1, required=True)
    platform = fields.Char('Platform', default='linux')
    template_id = fields.Integer('Template ID')
    logo = fields.Char('Logo URL')
    registry = fields.Char('Registry')
    image = fields.Char('Image')
    repository = fields.Text('Repository')
    categories = fields.Char('Categories')
    environment_variables = fields.Text('Environment Variables')
    volumes = fields.Text('Volumes')
    ports = fields.Text('Ports')
    note = fields.Text('Note')
    is_custom = fields.Boolean('Custom Template', default=False)
    
    server_id = fields.Many2one('j_portainer.server', string='Server', required=True, ondelete='cascade')
    
    def _get_api(self):
        """Get API client"""
        return self.env['j_portainer.api']
    
    def get_formatted_env(self):
        """Get formatted environment variables"""
        self.ensure_one()
        if not self.environment_variables:
            return ''
            
        try:
            env_data = json.loads(self.environment_variables)
            result = []
            
            for var in env_data:
                name = var.get('name', '')
                label = var.get('label', '')
                default = var.get('default', '')
                description = var.get('description', '')
                
                if label:
                    result.append(f"{label} ({name}): {default}")
                    if description:
                        result.append(f"  {description}")
                else:
                    result.append(f"{name}: {default}")
                    if description:
                        result.append(f"  {description}")
                        
            return '\n'.join(result)
        except Exception as e:
            _logger.error(f"Error formatting environment variables: {str(e)}")
            return self.environment_variables
            
    def get_formatted_volumes(self):
        """Get formatted volumes"""
        self.ensure_one()
        if not self.volumes:
            return ''
            
        try:
            volumes_data = json.loads(self.volumes)
            result = []
            
            for volume in volumes_data:
                container = volume.get('container', '')
                bind = volume.get('bind', '')
                readonly = volume.get('readonly', False)
                
                if bind and container:
                    if readonly:
                        result.append(f"{bind} -> {container} (read-only)")
                    else:
                        result.append(f"{bind} -> {container}")
                        
            return '\n'.join(result)
        except Exception as e:
            _logger.error(f"Error formatting volumes: {str(e)}")
            return self.volumes
            
    def get_formatted_ports(self):
        """Get formatted ports"""
        self.ensure_one()
        if not self.ports:
            return ''
            
        try:
            ports_data = json.loads(self.ports)
            result = []
            
            for port in ports_data:
                container = port.get('container', '')
                host = port.get('host', '')
                protocol = port.get('protocol', 'tcp')
                
                if container:
                    if host:
                        result.append(f"{host}:{container}/{protocol}")
                    else:
                        result.append(f"{container}/{protocol}")
                        
            return '\n'.join(result)
        except Exception as e:
            _logger.error(f"Error formatting ports: {str(e)}")
            return self.ports
            
    def get_formatted_categories(self):
        """Get formatted categories"""
        self.ensure_one()
        if not self.categories:
            return ''
            
        return self.categories.replace(',', ', ')
    
    def get_type_name(self):
        """Get type name"""
        self.ensure_one()
        types = {
            1: 'Container',
            2: 'Stack',
            3: 'App Template'
        }
        return types.get(self.template_type, 'Unknown')
        
    def action_deploy(self):
        """Action to deploy template"""
        self.ensure_one()
        
        return {
            'name': _('Deploy Template'),
            'type': 'ir.actions.act_window',
            'res_model': 'j_portainer.template.deploy.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_server_id': self.server_id.id,
                'default_template_id': self.id,
                'default_template_type': self.template_type,
                'default_template_title': self.title,
            }
        }
    
    def remove_custom_template(self):
        """Remove custom template
        Only works with custom templates
        """
        self.ensure_one()
        
        if not self.is_custom:
            raise UserError(_("Only custom templates can be removed"))
            
        try:
            api = self._get_api()
            result = api.template_action(
                self.server_id.id, self.template_id, 'delete')
                
            if result:
                # Delete the record
                self.unlink()
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Template Removed'),
                        'message': _('Template %s removed successfully') % self.title,
                        'sticky': False,
                        'type': 'success',
                    }
                }
            else:
                raise UserError(_("Failed to remove template"))
        except Exception as e:
            _logger.error(f"Error removing template {self.title}: {str(e)}")
            raise UserError(_("Error removing template: %s") % str(e))
    
    def action_refresh(self):
        """Refresh templates"""
        self.ensure_one()
        
        try:
            self.server_id.sync_templates()
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Templates Refreshed'),
                    'message': _('Templates refreshed successfully'),
                    'sticky': False,
                    'type': 'success',
                }
            }
        except Exception as e:
            _logger.error(f"Error refreshing templates: {str(e)}")
            raise UserError(_("Error refreshing templates: %s") % str(e))