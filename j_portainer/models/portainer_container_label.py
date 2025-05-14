#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)

class PortainerContainerLabel(models.Model):
    _name = 'j_portainer.container.label'
    _description = 'Portainer Container Label'
    _order = 'name'
    
    name = fields.Char('Label Name', required=True, index=True)
    value = fields.Char('Label Value', required=True)
    
    container_id = fields.Many2one('j_portainer.container', string='Container',
                                  required=True, ondelete='cascade', index=True)
    
    @api.depends('name', 'value')
    def _compute_display_name(self):
        """Compute display name for labels"""
        for label in self:
            label.display_name = f"{label.name}: {label.value}"