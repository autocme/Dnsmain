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
    
    name = fields.Char('Name', required=True)
    environment_id = fields.Integer('Environment ID', copy=False)
    url = fields.Char('URL')
    status = fields.Selection([
        ('up', 'Up'),
        ('down', 'Down')
    ], string='Status', default='down')
    type = fields.Integer('Type', help="1 = Local, 2 = Remote, 3 = Edge Agent, 4 = Azure ACI, 5 = Kubernetes")
    public_url = fields.Char('Public URL')
    group_id = fields.Integer('Group ID')
    group_name = fields.Char('Group')
    tags = fields.Char('Tags')
    details = fields.Text('Details')
    active = fields.Boolean('Active', default=True, 
                          help="If unchecked, it means this environment no longer exists in Portainer, "
                               "but it's kept in Odoo for reference and to maintain relationships with templates")
    last_sync = fields.Datetime('Last Synchronized', readonly=True)
    
    server_id = fields.Many2one('j_portainer.server', string='Server', required=True)
    
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
    
    @api.depends()
    def _compute_resource_counts(self):
        """Compute resource counts for each environment"""
        for env in self:
            # Containers
            containers = self.env['j_portainer.container'].search([
                ('server_id', '=', env.server_id.id),
                ('environment_id', '=', env.environment_id)
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
                ('environment_id', '=', env.environment_id)
            ])
            
            # Networks
            env.network_count = self.env['j_portainer.network'].search_count([
                ('server_id', '=', env.server_id.id),
                ('environment_id', '=', env.environment_id)
            ])
            
            # Stacks
            env.stack_count = self.env['j_portainer.stack'].search_count([
                ('server_id', '=', env.server_id.id),
                ('environment_id', '=', env.environment_id)
            ])
    
    def get_type_name(self):
        """Get type name"""
        self.ensure_one()
        types = {
            1: 'Local',
            2: 'Remote',
            3: 'Edge Agent',
            4: 'Azure ACI',
            5: 'Kubernetes'
        }
        return types.get(self.type, 'Unknown')
        
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