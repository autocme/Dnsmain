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
    size = fields.Float('Size (bytes)')
    shared_size = fields.Float('Shared Size (bytes)')
    virtual_size = fields.Float('Virtual Size (bytes)')
    labels = fields.Text('Labels')
    details = fields.Text('Details')
    in_use = fields.Boolean('In Use', default=False, help='Whether this image is being used by any containers')
    tags = fields.Html('Tags', compute='_compute_tags', store=True)
    layers = fields.Html('Layers', compute='_compute_layers', store=True, help='Image layers with size information')
    
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
                
    @api.depends('repository', 'tag')
    def _compute_tags(self):
        """Compute HTML formated tags for this image"""
        for image in self:
            if image.repository and image.tag:
                html = f"""
                <div class="mt-2">
                    <span class="badge badge-primary mb-1 mr-1">{image.repository}:{image.tag}</span>
                </div>
                """
                image.tags = html
            else:
                image.tags = "<div class='text-muted'>No tags available</div>"
                
    @api.depends('details')
    def _compute_layers(self):
        """Compute HTML formatted layers for this image
        Format: Order | Size | Layer Command
        """
        for image in self:
            if not image.details:
                image.layers = "<div class='text-muted'>No layer information available</div>"
                continue
                
            try:
                details = json.loads(image.details)
                
                # Extract layers information
                layers = []
                
                # Different Docker API versions have different fields
                # Try to get layers from RootFS or History
                if 'RootFS' in details and 'Layers' in details['RootFS']:
                    # Just layer IDs, not much to display
                    layer_ids = details['RootFS']['Layers']
                    for i, layer_id in enumerate(layer_ids):
                        # Try to get a size, but we can't reliably get it from RootFS
                        size = "-"
                        # Use short layer ID
                        short_id = layer_id.split(':')[-1][:12]
                        if len(short_id) > 12:
                            short_id = short_id[:12]
                        layers.append({
                            'order': i + 1,
                            'size': size,
                            'command': f"Layer ID: {short_id}"
                        })
                
                if 'History' in details and isinstance(details['History'], list):
                    # We have history which contains more info
                    history = details['History']
                    
                    # Get the actual image size for accurate layer size calculation
                    total_size = details.get('Size', 0)
                    
                    layers = []  # Reset layers if we have history
                    
                    for i, entry in enumerate(history):
                        # Skip empty layers created by cache or metadata
                        if 'empty_layer' in entry and entry['empty_layer']:
                            continue
                            
                        # Get the command that created this layer
                        created_by = entry.get('created_by', '')
                        if not created_by and 'Cmd' in entry:
                            created_by = ' '.join(entry['Cmd']) if isinstance(entry['Cmd'], list) else str(entry['Cmd'])
                            
                        # Clean up the command for display
                        if created_by.startswith('/bin/sh -c #(nop) '):
                            created_by = created_by[18:]
                        elif created_by.startswith('/bin/sh -c '):
                            created_by = 'RUN ' + created_by[10:]
                            
                        # Calculate a relative size - this is approximate since Docker doesn't expose layer sizes directly
                        size = entry.get('Size', total_size // (len(history) or 1))
                        
                        # Use the raw size value
                        size_str = str(size)
                            
                        layers.append({
                            'order': i + 1,
                            'size': size_str,
                            'command': created_by
                        })
                
                # Generate HTML table for layers
                if layers:
                    html = ['<table class="table table-sm table-hover">',
                            '<thead>',
                            '<tr>',
                            '<th width="5%">#</th>',
                            '<th width="15%">Size</th>',
                            '<th>Layer</th>',
                            '</tr>',
                            '</thead>',
                            '<tbody>']
                    
                    for layer in layers:
                        html.append('<tr>')
                        html.append(f'<td>{layer["order"]}</td>')
                        html.append(f'<td>{layer["size"]}</td>')
                        
                        # Make sure we escape any HTML in the command
                        command = layer["command"]
                        command = command.replace('<', '&lt;').replace('>', '&gt;')
                        
                        # Truncate very long commands
                        if len(command) > 100:
                            command = command[:97] + '...'
                            
                        html.append(f'<td class="text-monospace">{command}</td>')
                        html.append('</tr>')
                        
                    html.append('</tbody>')
                    html.append('</table>')
                    
                    image.layers = ''.join(html)
                else:
                    image.layers = "<div class='text-muted'>No layer information available</div>"
                    
            except Exception as e:
                _logger.error(f"Error computing layers for image {image.repository}:{image.tag}: {str(e)}")
                image.layers = f"<div class='text-danger'>Error computing layers: {str(e)}</div>"
    
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
    
    def pull(self):
        """Pull the latest version of the image"""
        self.ensure_one()
        
        try:
            api = self._get_api()
            image_name = f"{self.repository}:{self.tag}" if self.tag else self.repository
            
            result = api.image_action(
                self.server_id.id, 'pull', 
                endpoint=f"/endpoints/{self.environment_id}/docker/images/create",
                params={'fromImage': image_name}
            )
            
            if result.get('error'):
                raise UserError(_(f"Failed to pull image: {result.get('error')}"))
                
            # Refresh image data
            self.action_refresh()
            return True
            
        except Exception as e:
            raise UserError(_(f"Failed to pull image: {str(e)}"))
    
    def action_remove(self):
        """Remove this image"""
        self.ensure_one()
        
        # Store image information before attempting to delete
        image_name = f"{self.repository}:{self.tag}" if self.tag else self.repository
        
        try:
            api = self._get_api()
            result = api.image_action(
                self.server_id.id, 'remove',
                endpoint=f"/endpoints/{self.environment_id}/docker/images/{self.image_id}",
                params={'force': True}
            )
            
            if result.get('error'):
                # If Portainer deletion failed, don't delete from Odoo
                _logger.error(f"Failed to remove image {image_name} from Portainer: {result.get('error')}")
                raise UserError(_(f"Failed to remove image: {result.get('error')}"))
                
            # Only delete the Odoo record if Portainer deletion was successful
            # Create success notification first, before deleting the record
            message = {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Image Removed'),
                    'message': _('Image %s removed successfully') % image_name,
                    'sticky': False,
                    'type': 'success',
                }
            }
            
            # Now delete the record
            self.unlink()
            self.env.cr.commit()
            
            return message
            
        except Exception as e:
            _logger.error(f"Error removing image {image_name}: {str(e)}")
            raise UserError(_(f"Failed to remove image: {str(e)}"))
    
    def action_refresh(self):
        """Refresh image information"""
        self.ensure_one()
        
        try:
            # Use the server's sync_images method to refresh this image
            self.server_id.sync_images(self.environment_id)
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Image Refreshed'),
                    'message': _('Image information refreshed successfully'),
                    'sticky': False,
                    'type': 'success',
                }
            }
        except Exception as e:
            _logger.error(f"Error refreshing image {self.repository}:{self.tag}: {str(e)}")
            raise UserError(_("Error refreshing image: %s") % str(e))
    
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
                server_id, 
                'pull',
                endpoint=f"/endpoints/{environment_id}/docker/images/create",
                params={'fromImage': image_name}
            )
                
            if not result.get('error'):
                # Refresh the server images
                server = self.env['j_portainer.server'].browse(server_id)
                server.sync_images(environment_id)
                return True
            else:
                return False
        except Exception as e:
            _logger.error(f"Error pulling new image {repository}:{tag}: {str(e)}")
            return False