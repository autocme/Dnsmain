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
    environment_id = fields.Many2one(related='container_id.environment_id', string='Environment ID', store=True)
    
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

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to handle port changes synchronization to Portainer"""
        # If this is a sync operation from Portainer, save directly
        if self.env.context.get('sync_from_portainer'):
            return super(PortainerContainerPort, self).create(vals_list)
        
        # Create the port records
        result = super(PortainerContainerPort, self).create(vals_list)
        
        # Mark containers for port update
        containers = result.mapped('container_id')
        for container in containers:
            container._mark_ports_changed()
            
        return result

    def write(self, vals):
        """Override write to handle port changes synchronization to Portainer"""
        # If this is a sync operation from Portainer, save directly
        if self.env.context.get('sync_from_portainer'):
            return super(PortainerContainerPort, self).write(vals)
        
        # Store affected containers before update
        containers = self.mapped('container_id')
        
        # Perform the write operation
        result = super(PortainerContainerPort, self).write(vals)
        
        # Mark containers for port update
        for container in containers:
            container._mark_ports_changed()
            
        return result

    def unlink(self):
        """Override unlink to handle port removal synchronization to Portainer"""
        # If this is a sync operation from Portainer, remove directly
        if self.env.context.get('sync_from_portainer'):
            return super(PortainerContainerPort, self).unlink()
        
        # Store affected containers before deletion
        containers = self.mapped('container_id')
        
        # Perform the unlink operation
        result = super(PortainerContainerPort, self).unlink()
        
        # Mark containers for port update
        for container in containers:
            container._mark_ports_changed()
            
        return result