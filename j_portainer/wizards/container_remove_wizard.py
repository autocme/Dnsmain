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
            # If container is running and force is not checked, show a specific message
            container = self.container_id
            if container.state == 'running' and not self.force:
                raise UserError(_(
                    "Cannot remove running container. Either stop the container first or enable the 'Force' option."
                ))
                
            # Call the remove method on the container with the specified options
            result = container.remove(force=self.force, volumes=self.remove_volumes)
            
            # The container.remove method will handle displaying success messages
            return result
        except UserError:
            # Re-raise UserError directly to preserve the message
            raise
        except Exception as e:
            # Log the full error details
            _logger.error(f"Error removing container {self.container_name}: {str(e)}")
            
            # Provide more specific error messages based on common failures
            error_message = str(e)
            if "is running" in error_message or "running" in error_message:
                message = _(
                    "The container is currently running. Enable the 'Force' option to remove a running container."
                )
            elif "has active endpoints" in error_message or "endpoint" in error_message:
                message = _(
                    "Container has active network endpoints. Try enabling the 'Force' option."
                )
            elif "bind-mounted" in error_message or "mounted" in error_message:
                message = _(
                    "Container has mounted volumes. Enable the 'Remove Volumes' option to remove associated volumes."
                )
            elif "permission" in error_message or "access" in error_message:
                message = _(
                    "Permission denied. The server may not have sufficient permissions to remove this container."
                )
            else:
                message = _("Error removing container: %s") % error_message
                
            raise UserError(message)