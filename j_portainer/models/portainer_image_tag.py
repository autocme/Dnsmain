#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import random
import logging

_logger = logging.getLogger(__name__)

class PortainerImageTag(models.Model):
    _name = 'j_portainer.image.tag'
    _description = 'Portainer Image Tag'
    _rec_name = 'display_name'
    
    repository = fields.Char('Repository', required=True, index=True)
    tag = fields.Char('Tag', required=False, index=True, default='latest', 
                      help='Tag name. If not specified, "latest" will be used by default.')
    display_name = fields.Char('Display Name', compute='_compute_display_name', store=True, index=True)
    image_id = fields.Many2one('j_portainer.image', string='Image', required=True, ondelete='cascade',
                               default=lambda self: self.env.context.get('default_image_id'))
    color = fields.Integer('Color Index', default=lambda self: random.randint(1, 11))
    
    _sql_constraints = [
        ('tag_unique', 'unique(image_id, repository, tag)', 'Tag must be unique per repository within an image!')
    ]
    
    @api.depends('repository', 'tag')
    def _compute_display_name(self):
        """Compute display name based on repository and tag"""
        for tag in self:
            tag.display_name = f"{tag.repository}:{tag.tag}"
            
    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        """Override name_search to search in both repository and tag fields"""
        args = args or []
        domain = []
        
        if name:
            domain = ['|', '|',
                ('display_name', operator, name),
                ('repository', operator, name),
                ('tag', operator, name)]
                
        return self.search(domain + args, limit=limit).name_get()
    
    @api.model_create_multi
    def create(self, vals_list):
        """Override create to sync tag creation with Portainer"""
        for vals in vals_list:
            image = self.env['j_portainer.image'].browse(vals.get('image_id'))
            if not image.exists():
                raise UserError(_("Image not found"))
            
            # Validate repository and tag
            repository = vals.get('repository', '')
            if isinstance(repository, str):
                repository = repository.strip()
            else:
                repository = str(repository) if repository else ''
                
            tag = vals.get('tag', '')
            if isinstance(tag, str):
                tag = tag.strip()
            elif isinstance(tag, bool):
                tag = ''
            else:
                tag = str(tag) if tag else ''
            
            if not repository:
                raise UserError(_("Repository is required"))
            
            # Apply default tag logic like Portainer
            if not tag:
                tag = 'latest'
                vals['tag'] = tag
            
            # Skip Portainer API calls during sync operations
            # Check if this is a sync operation by looking for sync context
            if self.env.context.get('sync_operation'):
                continue  # Skip API call during sync
            
            # Prepare new tag name for Portainer
            new_tag_name = f"{repository}:{tag}"
            
            # Call Portainer API to tag the image only for manual tag creation
            try:
                api = self.env['j_portainer.api']
                response = api.direct_api_call(
                    image.server_id.id,
                    f"/api/endpoints/{image.environment_id.environment_id}/docker/images/{image.image_id}/tag",
                    method='POST',
                    params={
                        'repo': repository,
                        'tag': tag
                    }
                )
                
                # Check for successful response (201 Created for tag operation)
                if not response:
                    raise UserError(_("No response from Portainer API"))
                
                # Handle both dict response (from direct_api_call) and response object
                if isinstance(response, dict):
                    if not response.get('success', True):
                        error_msg = response.get('message', 'Unknown error from Portainer')
                        raise UserError(_("Failed to tag image in Portainer: %s") % error_msg)
                elif hasattr(response, 'status_code'):
                    if response.status_code != 201:
                        error_msg = _("Failed to tag image in Portainer")
                        if hasattr(response, 'text'):
                            error_msg += f": {response.text}"
                        raise UserError(error_msg)
                else:
                    raise UserError(_("Invalid response from Portainer API"))
                    
                _logger.info(f"Successfully tagged image {image.image_id} with {new_tag_name} in Portainer")
                
            except Exception as e:
                raise UserError(_("Failed to create tag in Portainer: %s") % str(e))
        
        # Only create Odoo records if Portainer API succeeded
        return super().create(vals_list)
    
    def unlink(self):
        """Override unlink to sync tag deletion with Portainer"""
        for tag in self:
            image = tag.image_id
            if not image.image_id:
                continue  # Skip if image not built yet
            
            # Call Portainer API to untag the image
            try:
                api = self.env['j_portainer.api']
                tag_name = f"{tag.repository}:{tag.tag}"
                
                response = api.direct_api_call(
                    image.server_id.id,
                    f"/api/endpoints/{image.environment_id.environment_id}/docker/images/{tag_name}",
                    method='DELETE',
                    params={'force': 'false'}
                )
                
                # Log the response for debugging
                _logger.info(f"Tag deletion response type: {type(response)}, content: {response}")
                
                # Check for successful response (200 OK or 204 No Content for delete operation)
                if response is None:
                    raise UserError(_("No response from Portainer API"))
                
                # Handle both dict response (from direct_api_call) and response object
                if isinstance(response, dict):
                    # Success dict from direct_api_call or error dict
                    success = response.get('success', True)
                    if success is False:
                        error_msg = response.get('message', 'Unknown error from Portainer')
                        raise UserError(_("Failed to remove tag from Portainer: %s") % error_msg)
                elif hasattr(response, 'status_code'):
                    # Raw response object
                    if response.status_code not in [200, 204]:
                        error_msg = _("Failed to remove tag from Portainer")
                        if hasattr(response, 'text'):
                            error_msg += f": {response.text}"
                        raise UserError(error_msg)
                elif response is True:
                    # Boolean True indicates success
                    pass
                else:
                    # Log unexpected response format but don't fail
                    _logger.warning(f"Unexpected response format from Portainer API: {type(response)} - {response}")
                    # Assume success if we got here without an exception
                    
                _logger.info(f"Successfully removed tag {tag_name} from Portainer")
                
            except Exception as e:
                raise UserError(_("Failed to remove tag from Portainer: %s") % str(e))
        
        # Only delete Odoo records if Portainer API succeeded
        return super().unlink()