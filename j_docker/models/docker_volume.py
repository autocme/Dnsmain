#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class DockerVolume(models.Model):
    _name = 'j_docker.docker_volume'
    _description = 'Docker Volume'
    _order = 'name'
    
    name = fields.Char('Name', required=True)
    driver = fields.Char('Driver')
    mountpoint = fields.Char('Mountpoint')
    created = fields.Datetime('Created')
    
    # Ensure server_id field is defined properly
    server_id = fields.Many2one('j_docker.docker_server', string='Server', required=True, ondelete='cascade')
    
    def inspect(self):
        """Get detailed volume information"""
        self.ensure_one()
        
        try:
            result = self.server_id.run_docker_command(f"volume inspect {self.name}")
            
            # Volume inspect returns an array with one object
            if isinstance(result, list) and len(result) > 0:
                return result[0]
            return result
        except Exception as e:
            _logger.error(f"Failed to inspect volume {self.name}: {str(e)}")
            raise UserError(_("Failed to inspect volume: %s") % str(e))
    
    def remove(self):
        """Remove the volume"""
        self.ensure_one()
        
        try:
            self.server_id.run_docker_command(f"volume rm {self.name}", as_json=False)
            # Delete the record
            self.unlink()
            return True
        except Exception as e:
            _logger.error(f"Failed to remove volume {self.name}: {str(e)}")
            raise UserError(_("Failed to remove volume: %s") % str(e))
            
    def prune(self):
        """Prune unused volumes on the server"""
        self.ensure_one()
        
        try:
            self.server_id.run_docker_command("volume prune -f", as_json=False)
            # Refresh volumes
            self.server_id.refresh_volumes()
            return True
        except Exception as e:
            _logger.error(f"Failed to prune volumes on server {self.server_id.name}: {str(e)}")
            raise UserError(_("Failed to prune volumes: %s") % str(e))