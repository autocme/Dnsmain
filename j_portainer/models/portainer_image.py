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
    all_tags = fields.Text('All Tags JSON', help='All tags for this image, stored as JSON array', groups='base.group_system')
    image_tag_ids = fields.One2many('j_portainer.image.tag', 'image_id', string='Image Tags')
    layers = fields.Html('Layers', compute='_compute_layers', store=True, help='Image layers with size information')
    labels_html = fields.Html('Labels Table', compute='_compute_labels_html', store=True, help='Image labels in table format')
    
    server_id = fields.Many2one('j_portainer.server', string='Server', required=True, ondelete='cascade')
    environment_id = fields.Integer('Environment ID', required=True)
    environment_name = fields.Char('Environment', required=True)
    last_sync = fields.Datetime('Last Synchronized', readonly=True)
    
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
                
    @api.model_create_multi
    def create(self, vals_list):
        """Override create to sync image tags"""
        records = super(PortainerImage, self).create(vals_list)
        for record in records:
            record._sync_image_tags()
        return records
    
    def write(self, vals):
        """Override write to sync image tags"""
        result = super(PortainerImage, self).write(vals)
        if 'all_tags' in vals:
            self._sync_image_tags()
        return result
    
    def _sync_image_tags(self):
        """Synchronize image tags from all_tags JSON data to image_tag_ids"""
        for image in self:
            if not image.all_tags:
                continue
            
            try:
                # Parse the all_tags JSON data
                all_tags_data = json.loads(image.all_tags)
                
                # Delete existing tags
                image.image_tag_ids.unlink()
                
                # Create new tag records
                tag_vals_list = []
                for tag_info in all_tags_data:
                    if isinstance(tag_info, dict) and 'repository' in tag_info and 'tag' in tag_info:
                        # New format with repository and tag separately
                        tag_vals_list.append({
                            'repository': tag_info['repository'],
                            'tag': tag_info['tag'],
                            'image_id': image.id
                        })
                
                if tag_vals_list:
                    self.env['j_portainer.image.tag'].create(tag_vals_list)
            except Exception as e:
                _logger.error(f"Error syncing image tags for image {image.id}: {str(e)}")
                
    @api.depends('details')
    def _compute_layers(self):
        """Compute HTML formatted layers for this image
        Format: Order | Size | Layer Command
        Starting with Order 0 to match Portainer's display
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
                # We'll use History for the primary layer info, then fall back to RootFS if needed
                use_rootfs = True
                
                if 'History' in details and isinstance(details['History'], list):
                    # We have history which contains more info
                    history = details['History']
                    use_rootfs = False
                    
                    # Get the actual image size for accurate layer size calculation
                    total_size = details.get('Size', 0)
                    
                    # Get size information for each layer - try to match Portainer's display
                    # Portainer typically shows size in MB for layers
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
                        
                        # Get size - if available directly, otherwise estimate
                        size = entry.get('Size', 0)
                        if size == 0 and total_size > 0:
                            # Estimate layer size as a fraction of total size
                            size = total_size // max(1, len(history))
                            
                        # Format size in MB with one decimal place like Portainer does
                        size_mb = size / (1024 * 1024)  # Convert bytes to MB
                        if size_mb < 0.1:
                            size_str = "< 0.1 MB"
                        else:
                            size_str = f"{size_mb:.1f} MB"
                            
                        layers.append({
                            'order': i,  # Start with 0 to match Portainer
                            'size': size_str,
                            'command': created_by
                        })
                
                # If we don't have history or layers is empty, fall back to RootFS
                if use_rootfs and 'RootFS' in details and 'Layers' in details['RootFS']:
                    layer_ids = details['RootFS']['Layers']
                    for i, layer_id in enumerate(layer_ids):
                        # For RootFS, we can't reliably get size, so show a placeholder
                        size_str = "Unknown"
                        
                        # Get full layer ID
                        full_id = layer_id.split(':')[-1]
                        
                        layers.append({
                            'order': i,  # Start with 0 to match Portainer
                            'size': size_str,
                            'command': full_id  # Use full layer ID for better matching with Portainer
                        })
                
                # Generate HTML table for layers
                if layers:
                    html = ['<table class="table table-sm table-hover">',
                            '<thead>',
                            '<tr>',
                            '<th width="5%">Order</th>',
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
                        
                        # Don't truncate commands to match Portainer's full display
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
            
    @api.depends('labels')
    def _compute_labels_html(self):
        """Compute HTML formatted table of labels"""
        for image in self:
            if not image.labels:
                image.labels_html = "<div class='text-muted'>No labels available</div>"
                continue
                
            try:
                labels_data = json.loads(image.labels)
                
                if not labels_data:
                    image.labels_html = "<div class='text-muted'>No labels available</div>"
                    continue
                    
                # Generate HTML table for labels
                html = ['<table class="table table-sm table-bordered table-striped">',
                        '<thead>',
                        '<tr>',
                        '<th width="30%">Label Name</th>',
                        '<th width="70%">Label Value</th>',
                        '</tr>',
                        '</thead>',
                        '<tbody>']
                
                for key, value in sorted(labels_data.items()):
                    # Escape HTML characters to prevent XSS
                    safe_key = str(key).replace('<', '&lt;').replace('>', '&gt;')
                    safe_value = str(value).replace('<', '&lt;').replace('>', '&gt;')
                    
                    html.append('<tr>')
                    html.append(f'<td class="text-monospace font-weight-bold">{safe_key}</td>')
                    html.append(f'<td class="text-monospace">{safe_value}</td>')
                    html.append('</tr>')
                    
                html.append('</tbody>')
                html.append('</table>')
                
                image.labels_html = ''.join(html)
            except Exception as e:
                _logger.error(f"Error computing labels HTML for image {image.id}: {str(e)}")
                image.labels_html = f"<div class='text-danger'>Error computing labels: {str(e)}</div>"
    
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
            
            # Handle different response formats from Portainer API
            has_error = False
            error_message = ""
            
            # Check if result is a dictionary with an error key
            if isinstance(result, dict) and 'error' in result:
                has_error = True
                error_message = result.get('error', 'Unknown error')
            # Check if result is a list (sometimes Docker API returns a list of deleted layers)
            elif isinstance(result, list):
                # If it's a list, this usually means success (list of deleted layers)
                has_error = False
                # Log the successful response for debugging
                _logger.info(f"Successfully removed image {image_name} from Portainer, response: {result}")
            # For any other non-success result format
            elif not result:
                has_error = True
                error_message = "Empty or null response from API"
            
            if has_error:
                # If Portainer deletion failed, don't delete from Odoo
                _logger.error(f"Failed to remove image {image_name} from Portainer: {error_message}")
                raise UserError(_(f"Failed to remove image: {error_message}"))
                
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