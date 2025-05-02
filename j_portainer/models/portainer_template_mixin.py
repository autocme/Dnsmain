#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
import json
import logging

_logger = logging.getLogger(__name__)

class PortainerTemplateMixin(models.AbstractModel):
    """Mixin class for common template functionality."""
    _name = 'j_portainer.template.mixin'
    _description = 'Common Template Functions'
    
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