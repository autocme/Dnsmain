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
                     
    # Relation to actual volume object (only for type='volume')
    volume_name_id = fields.Many2one('j_portainer.volume', string='Volume',
                                  domain="[('server_id', '=', server_id), ('name', '=', name)]",
                                  compute='_compute_volume_name_id', store=True)
    server_id = fields.Many2one(related='container_id.server_id', string='Server', store=True)
    environment_id = fields.Integer(related='container_id.environment_id', string='Environment ID', store=True)
    
    @api.depends('name', 'type', 'container_id.server_id', 'container_id.environment_id')
    def _compute_volume_name_id(self):
        """Compute the related volume record based on the name, server, and environment"""
        for record in self:
            # Only link to volume records for named volumes (not bind mounts, tmpfs, etc.)
            if record.type == 'volume' and record.name and record.container_id and record.container_id.server_id:
                # Find matching volume
                volume = self.env['j_portainer.volume'].search([
                    ('name', '=', record.name),
                    ('server_id', '=', record.container_id.server_id.id),
                    ('environment_id', '=', record.container_id.environment_id)
                ], limit=1)
                
                record.volume_name_id = volume.id if volume else False
            else:
                record.volume_name_id = False
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