#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class PortainerImageRemoveWizard(models.TransientModel):
    _name = 'j_portainer.image.remove.wizard'
    _description = 'Remove Image with Options'
    
    image_id = fields.Many2one('j_portainer.image', string='Image', required=True, readonly=True)
    image_name = fields.Char('Image Name', readonly=True)
    
    force = fields.Boolean('Force', default=False, 
                         help="Force removal of the image even if it has multiple tags or is used by containers")
    remove_unused = fields.Boolean('Remove Unused', default=False,
                                 help="Remove all dangling images (images without tags)")
    prune = fields.Boolean('Prune System', default=False,
                         help="Also delete dangling images (not associated with any container)")
    
    def action_remove(self):
        """Remove the image with specified options"""
        self.ensure_one()
        
        try:
            # Implement the image removal logic
            api = self.image_id._get_api()
            server_id = self.image_id.server_id.id
            environment_id = self.image_id.environment_id
            image_id = self.image_id.image_id
            
            # Handle different removal options
            if self.prune:
                # Call prune endpoint to remove unused images
                result = api.prune_images(server_id, environment_id)
                
                if result and isinstance(result, dict):
                    deleted_count = len(result.get('ImagesDeleted', []))
                    space_reclaimed = result.get('SpaceReclaimed', 0)
                    
                    # Format the space reclaimed in a human readable format
                    if space_reclaimed > 1024*1024*1024:
                        space_str = f"{space_reclaimed/(1024*1024*1024):.2f} GB"
                    elif space_reclaimed > 1024*1024:
                        space_str = f"{space_reclaimed/(1024*1024):.2f} MB"
                    elif space_reclaimed > 1024:
                        space_str = f"{space_reclaimed/1024:.2f} KB"
                    else:
                        space_str = f"{space_reclaimed} bytes"
                        
                    message = _('System pruned. Removed %s images, reclaimed %s') % (
                        deleted_count, space_str
                    )
                else:
                    message = _('System pruned successfully.')
            else:
                # Remove specific image
                endpoint = f'/api/endpoints/{environment_id}/docker/images/{image_id}'
                params = {
                    'force': self.force,
                }
                
                if self.remove_unused:
                    params['noprune'] = False
                
                response = self.image_id.server_id._make_api_request(endpoint, 'DELETE', params=params)
                
                if response.status_code != 200:
                    raise UserError(_("Failed to remove image: %s") % response.text)
                    
                # Remove image from Odoo database
                self.image_id.unlink()
                message = _('Image %s has been removed') % self.image_name
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Image Removed'),
                    'message': message,
                    'sticky': False,
                    'type': 'success',
                }
            }
        except Exception as e:
            _logger.error(f"Error removing image {self.image_name}: {str(e)}")
            raise UserError(_("Error removing image: %s") % str(e))