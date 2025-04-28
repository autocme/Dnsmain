#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class DockerNetwork(models.Model):
    _name = 'j_docker.docker_network'
    _description = 'Docker Network'
    _order = 'name'
    
    name = fields.Char('Name', required=True)
    network_id = fields.Char('Network ID', required=True)
    driver = fields.Char('Driver')
    scope = fields.Char('Scope')
    created = fields.Datetime('Created')
    
    # Ensure server_id field is defined properly
    server_id = fields.Many2one('j_docker.docker_server', string='Server', required=True, ondelete='cascade')
    
    def inspect(self):
        """Get detailed network information"""
        self.ensure_one()
        
        try:
            result = self.server_id.run_docker_command(f"network inspect {self.network_id}")
            
            # Network inspect returns an array with one object
            if isinstance(result, list) and len(result) > 0:
                return result[0]
            return result
        except Exception as e:
            _logger.error(f"Failed to inspect network {self.network_id}: {str(e)}")
            raise UserError(_("Failed to inspect network: %s") % str(e))
    
    def remove(self):
        """Remove the network"""
        self.ensure_one()
        
        try:
            self.server_id.run_docker_command(f"network rm {self.network_id}", as_json=False)
            # Delete the record
            self.unlink()
            return True
        except Exception as e:
            _logger.error(f"Failed to remove network {self.network_id}: {str(e)}")
            raise UserError(_("Failed to remove network: %s") % str(e))
            
    def prune(self):
        """Prune unused networks on the server"""
        self.ensure_one()
        
        try:
            self.server_id.run_docker_command("network prune -f", as_json=False)
            # Refresh networks
            self.server_id.refresh_networks()
            return True
        except Exception as e:
            _logger.error(f"Failed to prune networks on server {self.server_id.name}: {str(e)}")
            raise UserError(_("Failed to prune networks: %s") % str(e))