#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import json
import logging

_logger = logging.getLogger(__name__)

class DockerContainer(models.Model):
    _name = 'j_docker.docker_container'
    _description = 'Docker Container'
    _order = 'name'
    
    name = fields.Char('Name', required=True)
    container_id = fields.Char('Container ID', required=True)
    image = fields.Char('Image')
    image_id = fields.Char('Image ID')
    status = fields.Char('Status')
    state = fields.Selection([
        ('running', 'Running'),
        ('stopped', 'Stopped'),
        ('paused', 'Paused'),
        ('exited', 'Exited'),
        ('created', 'Created'),
        ('restarting', 'Restarting'),
        ('dead', 'Dead')
    ], string='State', default='created')
    ports = fields.Char('Ports')
    created = fields.Datetime('Created')
    command = fields.Char('Command')
    
    # Ensure server_id field is defined properly
    server_id = fields.Many2one('j_docker.docker_server', string='Server', required=True, ondelete='cascade')
    
    # Add necessary methods
    def inspect(self):
        """Get detailed container information"""
        self.ensure_one()
        
        try:
            result = self.server_id.run_docker_command(f"container inspect {self.container_id}")
            
            # Container inspect returns an array with one object
            if isinstance(result, list) and len(result) > 0:
                return result[0]
            return result
        except Exception as e:
            _logger.error(f"Failed to inspect container {self.container_id}: {str(e)}")
            raise UserError(_("Failed to inspect container: %s") % str(e))
    
    def start(self):
        """Start the container"""
        self.ensure_one()
        
        try:
            self.server_id.run_docker_command(f"container start {self.container_id}", as_json=False)
            # Update state
            self.write({'state': 'running'})
            return True
        except Exception as e:
            _logger.error(f"Failed to start container {self.container_id}: {str(e)}")
            raise UserError(_("Failed to start container: %s") % str(e))
    
    def stop(self):
        """Stop the container"""
        self.ensure_one()
        
        try:
            self.server_id.run_docker_command(f"container stop {self.container_id}", as_json=False)
            # Update state
            self.write({'state': 'stopped'})
            return True
        except Exception as e:
            _logger.error(f"Failed to stop container {self.container_id}: {str(e)}")
            raise UserError(_("Failed to stop container: %s") % str(e))
    
    def restart(self):
        """Restart the container"""
        self.ensure_one()
        
        try:
            self.server_id.run_docker_command(f"container restart {self.container_id}", as_json=False)
            # Update state
            self.write({'state': 'running'})
            return True
        except Exception as e:
            _logger.error(f"Failed to restart container {self.container_id}: {str(e)}")
            raise UserError(_("Failed to restart container: %s") % str(e))
    
    def remove(self):
        """Remove the container"""
        self.ensure_one()
        
        try:
            self.server_id.run_docker_command(f"container rm {self.container_id}", as_json=False)
            # Delete the record
            self.unlink()
            return True
        except Exception as e:
            _logger.error(f"Failed to remove container {self.container_id}: {str(e)}")
            raise UserError(_("Failed to remove container: %s") % str(e))
            
    def get_logs(self, tail=100):
        """Get container logs"""
        self.ensure_one()
        
        try:
            logs = self.server_id.run_docker_command(f"container logs --tail={tail} {self.container_id}", as_json=False)
            return logs
        except Exception as e:
            _logger.error(f"Failed to get logs for container {self.container_id}: {str(e)}")
            raise UserError(_("Failed to get container logs: %s") % str(e))