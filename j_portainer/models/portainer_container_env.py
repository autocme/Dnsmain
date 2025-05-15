#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import json
import logging

_logger = logging.getLogger(__name__)

class PortainerContainerEnv(models.Model):
    _name = 'j_portainer.container.env'
    _description = 'Portainer Container Environment Variable'
    _order = 'name'
    
    name = fields.Char('Name', required=True, help="Environment variable name")
    value = fields.Char('Value', help="Environment variable value")
    container_id = fields.Many2one('j_portainer.container', string='Container', 
                                  required=True, ondelete='cascade',
                                  help="Container this environment variable belongs to")
    
    _sql_constraints = [
        ('unique_env_per_container', 'UNIQUE(name, container_id)', 
         'Environment variable names must be unique per container')
    ]
    
    def name_get(self):
        """Custom name_get method to display name and value"""
        result = []
        for env in self:
            name = f"{env.name}"
            if env.value:
                name += f": {env.value}"
            result.append((env.id, name))
        return result