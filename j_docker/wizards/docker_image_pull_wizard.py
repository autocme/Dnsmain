#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging
import re

_logger = logging.getLogger(__name__)

class DockerImagePullWizard(models.TransientModel):
    _name = 'j_docker.image.pull.wizard'
    _description = 'Pull Docker Image Wizard'
    
    server_id = fields.Many2one('j_docker.docker_server', string='Server', required=True)
    image_name = fields.Char('Image Name', required=True,
                            help="Image name from Docker Hub (e.g., nginx, ubuntu)")
    tag = fields.Char('Tag', default='latest',
                     help="Image tag (e.g., latest, 1.21, 20.04)")
    full_name = fields.Char('Full Image Name', compute='_compute_full_name', store=True)
    pull_progress = fields.Text('Pull Progress', readonly=True)
    state = fields.Selection([
        ('name', 'Enter Image Details'),
        ('pulling', 'Pulling Image'),
        ('done', 'Complete')
    ], default='name', string='Status')
    
    @api.depends('image_name', 'tag')
    def _compute_full_name(self):
        for wizard in self:
            if wizard.image_name:
                if wizard.tag:
                    wizard.full_name = f"{wizard.image_name}:{wizard.tag}"
                else:
                    wizard.full_name = f"{wizard.image_name}:latest"
            else:
                wizard.full_name = False
    
    def validate_image_name(self):
        """Validate Docker image name format"""
        self.ensure_one()
        
        # Basic validation for Docker image name
        pattern = r'^[a-z0-9]+(([._-][a-z0-9]+)+)?(/[a-z0-9]+(([._-][a-z0-9]+)+)?)*$'
        if not re.match(pattern, self.image_name):
            raise UserError(_("Invalid image name format. Docker image names must be lowercase and may contain digits, dashes, underscores, and dots."))
        
        # Basic validation for tag
        if self.tag and not re.match(r'^[a-zA-Z0-9_.-]+$', self.tag):
            raise UserError(_("Invalid tag format. Tags may contain letters, digits, underscores, periods, and dashes."))
        
        return True
        
    def pull_image(self):
        """Pull Docker image from Docker Hub"""
        self.ensure_one()
        
        try:
            # Validate image name and tag
            self.validate_image_name()
            
            # Update state to pulling
            self.write({'state': 'pulling'})
            self._cr.commit()  # Commit transaction to update UI
            
            # Prepare image name with tag
            image_name = self.full_name
            
            # Pull the image
            output = self.server_id.run_docker_command(f"image pull {image_name}", as_json=False)
            self.write({
                'pull_progress': output,
                'state': 'done'
            })
            
            # Refresh server images to see the new image
            self.server_id.refresh_images()
            
            # Return success message
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Image Pulled'),
                    'message': _('Successfully pulled image %s') % image_name,
                    'sticky': False,
                    'type': 'success',
                }
            }
        except Exception as e:
            _logger.error(f"Failed to pull image {self.full_name}: {str(e)}")
            self.write({
                'pull_progress': str(e),
                'state': 'name'
            })
            raise UserError(_("Failed to pull image: %s") % str(e))
    
    def action_back_to_name(self):
        """Go back to name input step"""
        self.ensure_one()
        self.write({'state': 'name'})
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'j_docker.image.pull.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_close(self):
        """Close the wizard and refresh image list"""
        return {'type': 'ir.actions.act_window_close'}