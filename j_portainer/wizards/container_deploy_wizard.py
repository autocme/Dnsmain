# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class ContainerDeployWizard(models.TransientModel):
    _name = 'j_portainer.container.deploy.wizard'
    _description = 'Container Deploy Confirmation Wizard'

    container_id = fields.Many2one('j_portainer.container', string='Container', required=True)
    container_name = fields.Char('Container Name', readonly=True)
    
    def action_confirm_deploy(self):
        """Confirm deployment - remove existing container and recreate"""
        self.ensure_one()
        
        container = self.container_id
        if not container:
            raise UserError(_("Container not found"))
        
        try:
            # Remove existing container if it exists
            if container.container_id:
                _logger.info(f"Removing existing container {container.name} before redeployment")
                container.remove(force=True)
            
            # Deploy the container with new configuration
            result = container._deploy_container()
            
            # Clear pending changes after successful deployment
            container.write({
                'has_pending_changes': False,
                'original_config': False,
            })
            
            return result
            
        except Exception as e:
            _logger.error(f"Error during container redeployment: {str(e)}")
            raise UserError(_("Error during container redeployment: %s") % str(e))
    
    def action_cancel(self):
        """Cancel deployment"""
        return {'type': 'ir.actions.act_window_close'}