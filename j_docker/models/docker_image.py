#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class DockerImage(models.Model):
    _name = 'j_docker.docker_image'
    _description = 'Docker Image'
    _order = 'repository'
    
    repository = fields.Char('Repository', required=True)
    tag = fields.Char('Tag')
    image_id = fields.Char('Image ID', required=True)
    created = fields.Datetime('Created')
    size = fields.Char('Size')
    
    # Ensure server_id field is defined properly
    server_id = fields.Many2one('j_docker.docker_server', string='Server', required=True, ondelete='cascade')
    
    @api.depends('repository', 'tag')
    def _compute_display_name(self):
        """Compute display name based on repository and tag"""
        for image in self:
            if image.tag:
                image.display_name = f"{image.repository}:{image.tag}"
            else:
                image.display_name = image.repository
    
    # Override name_get to display repository:tag
    def name_get(self):
        result = []
        for image in self:
            name = image.repository
            if image.tag:
                name = f"{name}:{image.tag}"
            result.append((image.id, name))
        return result
    
    def inspect(self):
        """Get detailed image information"""
        self.ensure_one()
        
        try:
            result = self.server_id.run_docker_command(f"image inspect {self.image_id}")
            
            # Image inspect returns an array with one object
            if isinstance(result, list) and len(result) > 0:
                return result[0]
            return result
        except Exception as e:
            _logger.error(f"Failed to inspect image {self.image_id}: {str(e)}")
            raise UserError(_("Failed to inspect image: %s") % str(e))
    
    def remove(self):
        """Remove the image"""
        self.ensure_one()
        
        try:
            self.server_id.run_docker_command(f"image rm {self.image_id}", as_json=False)
            # Delete the record
            self.unlink()
            return True
        except Exception as e:
            _logger.error(f"Failed to remove image {self.image_id}: {str(e)}")
            raise UserError(_("Failed to remove image: %s") % str(e))
    
    def pull(self):
        """Pull the latest version of the image"""
        self.ensure_one()
        
        try:
            # Construct image name with tag if available
            image_name = self.repository
            if self.tag:
                image_name = f"{image_name}:{self.tag}"
                
            self.server_id.run_docker_command(f"image pull {image_name}", as_json=False)
            # Refresh the server images
            self.server_id.refresh_images()
            return True
        except Exception as e:
            _logger.error(f"Failed to pull image {self.repository}: {str(e)}")
            raise UserError(_("Failed to pull image: %s") % str(e))
    
    @api.model
    def pull_from_docker_hub(self, server_id, image_name, tag='latest'):
        """Pull an image from Docker Hub by name and tag
        
        Args:
            server_id: ID of the Docker server to use
            image_name: Name of the image (e.g., nginx, ubuntu)
            tag: Tag of the image (e.g., latest, alpine)
            
        Returns:
            bool: True if successful
            
        Raises:
            UserError: If pull fails
        """
        try:
            # Get server
            server = self.env['j_docker.docker_server'].browse(server_id)
            if not server:
                raise UserError(_("Server not found"))
                
            # Construct full image name
            full_image_name = f"{image_name}:{tag}" if tag else f"{image_name}:latest"
            
            # Pull the image
            server.run_docker_command(f"image pull {full_image_name}", as_json=False)
            
            # Refresh the server images
            server.refresh_images()
            
            return True
        except Exception as e:
            _logger.error(f"Failed to pull image {image_name}:{tag}: {str(e)}")
            raise UserError(_("Failed to pull image: %s") % str(e))