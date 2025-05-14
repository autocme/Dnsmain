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
                                  required=True, ondelete='cascade', index=True)
    
    # Volume mapping information
    type = fields.Selection([
        ('volume', 'Named Volume'),
        ('bind', 'Bind Mount'),
        ('tmpfs', 'Tmpfs'),
        ('npipe', 'Named Pipe'),
        ('other', 'Other')
    ], string='Type', required=True, default='volume')
    
    name = fields.Char('Volume Name/Source', required=True, 
                     help="Name of the volume for named volumes, or path for bind mounts")
    container_path = fields.Char('Container Path', required=True,
                               help="Path inside the container where the volume is mounted")
    mode = fields.Char('Access Mode', default='rw',
                     help="Access mode of the mount (e.g., rw, ro)")
    
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