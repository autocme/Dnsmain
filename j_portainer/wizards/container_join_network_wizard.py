#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class ContainerJoinNetworkWizard(models.TransientModel):
    _name = 'j_portainer.container.join.network.wizard'
    _description = 'Join Container to Network Wizard'
    
    container_id = fields.Many2one('j_portainer.container', string='Container', required=True,
                                   readonly=True, ondelete='cascade')
    server_id = fields.Many2one(related='container_id.server_id', string='Server', readonly=True)
    environment_id = fields.Many2one(related='container_id.environment_id', string='Environment ID', readonly=True)
    environment_name = fields.Char(related='environment_id.name', string='Environment', readonly=True)
    
    # Available networks to join - domain is set to only show networks from the same environment
    network_id = fields.Many2one('j_portainer.network', string='Network', required=True,
                               domain="[('server_id', '=', server_id), ('environment_id', '=', environment_id)]")
    
    # Fields for IP address and aliases have been removed as per requirements
    
    def action_join_network(self):
        """Join the container to the selected network"""
        self.ensure_one()
        
        # Check if container is already connected to this network
        existing_connection = self.env['j_portainer.container.network'].search([
            ('container_id', '=', self.container_id.id),
            ('network_id', '=', self.network_id.id)
        ], limit=1)
        
        if existing_connection:
            raise UserError(_("This container is already connected to network '%s'") % self.network_id.name)
        
        try:
            # Network configuration is empty as IP and aliases have been removed
            config = {}
            
            # Call API to connect container to network
            api = self.env['j_portainer.api']
            result = api.connect_container_to_network(
                self.server_id.id,
                self.environment_id,
                self.network_id.network_id,
                self.container_id.container_id,
                config
            )
            
            if result:
                # Create network connection record (without ip_address)
                self.env['j_portainer.container.network'].create({
                    'container_id': self.container_id.id,
                    'network_id': self.network_id.id,
                })
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Network Connected'),
                        'message': _('Container connected to network %s successfully') % self.network_id.name,
                        'sticky': False,
                        'type': 'success',
                    }
                }
            else:
                raise UserError(_("Failed to connect container to network '%s'") % self.network_id.name)
                
        except Exception as e:
            _logger.error(f"Error connecting container to network: {str(e)}")
            raise UserError(_("Error connecting to network: %s") % str(e))