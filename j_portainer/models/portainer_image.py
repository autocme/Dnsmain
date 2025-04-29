#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import json
import logging

_logger = logging.getLogger(__name__)

class PortainerImage(models.Model):
    _name = 'j_portainer.image'
    _description = 'Portainer Image'
    _order = 'repository, tag'
    
    repository = fields.Char('Repository', required=True)
    tag = fields.Char('Tag', required=True)
    image_id = fields.Char('Image ID', required=True)
    created = fields.Datetime('Created')
    size = fields.Integer('Size (bytes)')
    shared_size = fields.Integer('Shared Size (bytes)')
    virtual_size = fields.Integer('Virtual Size (bytes)')
    labels = fields.Text('Labels')
    details = fields.Text('Details')
    
    server_id = fields.Many2one('j_portainer.server', string='Server', required=True, ondelete='cascade')
    environment_id = fields.Integer('Environment ID', required=True)
    environment_name = fields.Char('Environment', required=True)
    
    def _get_api(self):
        """Get API client"""
        return self.env['j_portainer.api']
    
    @api.depends('repository', 'tag')
    def _compute_display_name(self):
        """Compute display name based on repository and tag"""
        for image in self:
            if image.tag:
                image.display_name = f"{image.repository}:{image.tag}"
            else:
                image.display_name = image.repository
    
    def name_get(self):
        """Override name_get to display repository:tag"""
        result = []
        for image in self:
            name = image.repository
            if image.tag:
                name = f"{name}:{image.tag}"
            result.append((image.id, name))
        return result
    
    def get_formatted_labels(self):
        """Get formatted image labels"""
        self.ensure_one()
        if not self.labels:
            return ''
            
        try:
            labels_data = json.loads(self.labels)
            formatted_labels = [f"{key}: {value}" for key, value in labels_data.items()]
            return '\n'.join(formatted_labels)
        except Exception as e:
            _logger.error(f"Error formatting labels: {str(e)}")
            return self.labels
    
    def get_size_human(self):
        """Get human-readable size"""
        self.ensure_one()
        
        if not self.size:
            return '0 B'
            
        size = self.size
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
            
        return f"{size:.2f} PB"
    
    def pull(self):
        """Pull the latest version of the image"""
        self.ensure_one()
        
        try:
            api = self._get_api()
            image_name = f"{self.repository}:{self.tag}" if self.tag else self.repository
            
            result = api.image_action(
                self.server_id.id, self.environment_id, image_name, 'pull')
                
            if result:
                # Refresh the server images
                self.server_id.sync_images(self.environment_id)
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Image Pulled'),
                        'message': _('Image %s pulled successfully') % image_name,
                        'sticky': False,
                        'type': 'success',
                    }
                }
            else:
                raise UserError(_("Failed to pull image"))
        except Exception as e:
            _logger.error(f"Error pulling image {self.repository}:{self.tag}: {str(e)}")
            raise UserError(_("Error pulling image: %s") % str(e))
    
    def remove(self, force=False, no_prune=False):
        """Remove the image
        
        Args:
            force (bool): Force removal
            no_prune (bool): Don't delete untagged parent images
        """
        self.ensure_one()
        
        try:
            api = self._get_api()
            params = {
                'force': force,
                'noprune': no_prune
            }
            
            result = api.image_action(
                self.server_id.id, self.environment_id, self.image_id, 'delete', params=params)
                
            if result:
                # Delete the record
                self.unlink()
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Image Removed'),
                        'message': _('Image %s:%s removed successfully') % (self.repository, self.tag),
                        'sticky': False,
                        'type': 'success',
                    }
                }
            else:
                raise UserError(_("Failed to remove image"))
        except Exception as e:
            _logger.error(f"Error removing image {self.repository}:{self.tag}: {str(e)}")
            raise UserError(_("Error removing image: %s") % str(e))
    
    def action_remove_with_options(self):
        """Action to show image removal options"""
        self.ensure_one()
        
        return {
            'name': _('Remove Image'),
            'type': 'ir.actions.act_window',
            'res_model': 'j_portainer.image.remove.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_image_id': self.id,
                'default_image_name': f"{self.repository}:{self.tag}",
            }
        }
        
    @api.model
    def pull_new_image(self, server_id, environment_id, repository, tag='latest'):
        """Pull a new image
        
        Args:
            server_id: ID of the server to pull the image to
            environment_id: ID of the environment to pull the image to
            repository: Repository to pull
            tag: Tag to pull (default: 'latest')
            
        Returns:
            bool: True if successful
        """
        try:
            api = self._get_api()
            image_name = f"{repository}:{tag}" if tag else repository
            
            result = api.image_action(
                server_id, environment_id, image_name, 'pull')
                
            if result:
                # Refresh the server images
                server = self.env['j_portainer.server'].browse(server_id)
                server.sync_images(environment_id)
                
                return True
            else:
                return False
        except Exception as e:
            _logger.error(f"Error pulling new image {repository}:{tag}: {str(e)}")
            return False