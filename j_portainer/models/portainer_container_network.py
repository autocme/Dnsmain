#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)

class PortainerContainerNetwork(models.Model):
    _name = 'j_portainer.container.network'
    _description = 'Portainer Container Network Connection'
    _order = 'network_name'
    
    container_id = fields.Many2one('j_portainer.container', string='Container',
                                  required=True, ondelete='cascade', index=True)
    network_id = fields.Many2one('j_portainer.network', string='Network',
                               required=True, ondelete='cascade', index=True)
    network_name = fields.Char(related='network_id.name', string='Network Name', store=True)
    
    # Network configuration for this container
    ip_address = fields.Char('IP Address')
    gateway = fields.Char('Gateway')
    mac_address = fields.Char('MAC Address')
    
    # Other network details
    driver = fields.Char(related='network_id.driver', string='Driver', readonly=True)
    scope = fields.Char(related='network_id.scope', string='Scope', readonly=True)
    
    # Display name computed field
    display_name = fields.Char('Display Name', compute='_compute_display_name')
    
    _sql_constraints = [
        ('container_network_unique', 'UNIQUE(container_id, network_id)', 
         'Container can only be connected to a network once!')
    ]
    
    @api.depends('network_id.name', 'ip_address')
    def _compute_display_name(self):
        """Compute display name for network connection"""
        for network in self:
            if network.ip_address:
                network.display_name = f"{network.network_id.name} ({network.ip_address})"
            else:
                network.display_name = network.network_id.name
    
    def disconnect_network(self):
        """Disconnect container from this network"""
        self.ensure_one()
        
        try:
            api = self.env['j_portainer.api']
            result = api.disconnect_container_from_network(
                self.container_id.server_id.id,
                self.container_id.environment_id,
                self.network_id.network_id,
                self.container_id.container_id
            )
            
            if result:
                # Remove the record on success
                self.unlink()
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Network Disconnected'),
                        'message': _('Container disconnected from network %s successfully') % self.network_id.name,
                        'sticky': False,
                        'type': 'success',
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Network Disconnect Failed'),
                        'message': _('Failed to disconnect from network %s') % self.network_id.name,
                        'sticky': False,
                        'type': 'danger',
                    }
                }
        except Exception as e:
            _logger.error(f"Error disconnecting container from network: {str(e)}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': str(e),
                    'sticky': False,
                    'type': 'danger',
                }
            }