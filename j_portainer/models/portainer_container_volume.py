#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)

class PortainerContainerVolume(models.Model):
    _name = 'j_portainer.container.volume'
    _description = 'Portainer Container Volume Mapping'
    _order = 'container_path'
    
    container_id = fields.Many2one('j_portainer.container', string='Container',
                                  required=True, readonly=True, ondelete='cascade', index=True)
    
    # Volume mapping information
    type = fields.Selection([
        ('volume', 'Volume'),
        ('bind', 'Bind'),
    ], string='Type', required=True, default='volume')
    
    name = fields.Char('Path On Host',
                     help="Name of path for bind mounts")
                     
    # Direct volume selection for type='volume'
    volume_id = fields.Many2one('j_portainer.volume', string='Volume',
                              domain="[('server_id', '=', server_id), ('environment_id', '=', environment_id)]")
    server_id = fields.Many2one(related='container_id.server_id', string='Server', store=True)
    environment_id = fields.Integer(related='container_id.environment_id', string='Environment ID', store=True)
    
    @api.onchange('volume_id')
    def _onchange_volume_id(self):
        """When volume is selected, copy its name to the name field"""
        for record in self:
            if record.volume_id:
                record.name = record.volume_id.name
                
    @api.onchange('type')
    def _onchange_type(self):
        """Reset fields when type changes between volume and bind"""
        for record in self:
            # Reset volume-specific or bind-specific fields when switching types
            if record.type == 'volume':
                record.name = ''  # Clear the bind path
            elif record.type == 'bind':
                record.volume_id = False  # Clear the volume selection
    container_path = fields.Char('Container Path', required=True,
                               help="Path inside the container where the volume is mounted")
    mode = fields.Selection([
        ('rw', 'Writable'),
        ('ro', 'Read-only'),
        ('z', 'z'),
    ], string='Access Mode', default='rw',
        help="Access mode of the volume or bind mount")
    
    driver = fields.Char('Driver', help="Driver used for this volume")
    
    display_name = fields.Char('Display Name', compute='_compute_display_name')
    
    @api.depends('type', 'name', 'container_path')
    def _compute_display_name(self):
        """Compute display name for volume mappings"""
        for volume in self:
            if volume.type == 'volume':
                volume.display_name = f"{volume.container_path} → volume: {volume.name}"
            elif volume.type == 'bind':
                volume.display_name = f"{volume.container_path} → host: {volume.name}"
            else:
                volume.display_name = f"{volume.container_path} → {volume.type}: {volume.name}"
                
    def view_related_container(self):
        """Open the related container form view"""
        self.ensure_one()
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'j_portainer.container',
            'res_id': self.container_id.id,
            'view_mode': 'form',
            'target': 'current',
        }