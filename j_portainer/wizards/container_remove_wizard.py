#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class PortainerContainerRemoveWizard(models.TransientModel):
    _name = 'j_portainer.container.remove.wizard'
    _description = 'Remove Container with Options'
    
    container_id = fields.Many2one('j_portainer.container', string='Container', required=True, readonly=True)
    container_name = fields.Char('Container Name', readonly=True)
    
    force = fields.Boolean('Force', default=False, 
                         help="Force removal of the container even if it is running")
    remove_volumes = fields.Boolean('Remove Volumes', default=False,
                                  help="Remove anonymous volumes associated with the container")
    
    def action_remove(self):
        """Remove the container with specified options"""
        self.ensure_one()
        
        try:
            # Call the remove method on the container with the specified options
            self.container_id.remove(force=self.force, volumes=self.remove_volumes)
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Container Removed'),
                    'message': _('Container %s has been removed') % self.container_name,
                    'sticky': False,
                    'type': 'success',
                }
            }
        except Exception as e:
            _logger.error(f"Error removing container {self.container_name}: {str(e)}")
            raise UserError(_("Error removing container: %s") % str(e))