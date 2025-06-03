#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)

class PortainerContainerPort(models.Model):
    _name = 'j_portainer.container.port'
    _description = 'Portainer Container Port Mapping'
    _order = 'container_port'
    
    container_id = fields.Many2one('j_portainer.container', string='Container',
                                 required=True, index=True, ondelete='cascade')
    
    # Port mapping information
    container_port = fields.Integer('Container Port', required=True, 
                                   help="Port inside the container")
    host_port = fields.Integer('Host Port', 
                              help="Port on the host machine, may be different from container port")
    protocol = fields.Selection([
        ('tcp', 'TCP'),
        ('udp', 'UDP')
    ], string='Protocol', required=True, default='tcp')
    
    # IP binding
    host_ip = fields.Char('Host IP', 
                         help="IP address the port is bound to on the host, empty means all interfaces")
    
    # Related information
    server_id = fields.Many2one(related='container_id.server_id', string='Server', store=True)
    environment_id = fields.Integer(related='container_id.environment_id', string='Environment ID', store=True)
    
    # Computed fields for display
    display_name = fields.Char('Display Name', compute='_compute_display_name')
    
    @api.depends('container_port', 'host_port', 'protocol', 'host_ip')
    def _compute_display_name(self):
        """Compute readable display name for port mapping"""
        for port in self:
            if port.host_port:
                if port.host_ip:
                    port.display_name = f"{port.host_ip}:{port.host_port}->{port.container_port}/{port.protocol}"
                else:
                    port.display_name = f"{port.host_port}->{port.container_port}/{port.protocol}"
            else:
                port.display_name = f"{port.container_port}/{port.protocol} (not published)"