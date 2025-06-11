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
    
    _sql_constraints = [
        ('unique_image_per_environment', 'unique(image_id, environment_id)', 
         'An image with this ID already exists in this environment')
    ]
    
    repository = fields.Char('Repository', required=True)
    tag = fields.Char('Tag', required=True)
    image_id = fields.Char('Image ID', required=False, readonly=True, copy=False)
    created = fields.Datetime('Created')
    size = fields.Float('Size (bytes)')
    shared_size = fields.Float('Shared Size (bytes)')
    virtual_size = fields.Float('Virtual Size (bytes)')
    size_formatted = fields.Char('Size', compute='_compute_formatted_sizes', store=True)
    shared_size_formatted = fields.Char('Shared Size', compute='_compute_formatted_sizes', store=True)
    virtual_size_formatted = fields.Char('Virtual Size', compute='_compute_formatted_sizes', store=True)
    labels = fields.Text('Labels')
    details = fields.Text('Details')
    in_use = fields.Boolean('In Use', default=False, help='Whether this image is being used by any containers')
    all_tags = fields.Text('All Tags JSON', help='All tags for this image, stored as JSON array', groups='base.group_system')
    image_tag_ids = fields.One2many('j_portainer.image.tag', 'image_id', string='Image Tags')
    enhanced_layers_data = fields.Text('Enhanced Layers Data', help='Enhanced layer data from Docker Image History API stored as JSON')
    layers = fields.Html('Layers', compute='_compute_layers', store=True, help='Image layers with size information')
    labels_html = fields.Html('Labels Table', compute='_compute_labels_html', store=True, help='Image labels in table format')
    env_html = fields.Html('Environment Variables', compute='_compute_env_html', store=True, help='Image environment variables in table format')
    build_info = fields.Text('Build', compute='_compute_build_info', store=True, help='Docker build information')
    
    server_id = fields.Many2one('j_portainer.server', string='Server', required=True,
                                default=lambda self: self.env['j_portainer.server'].search([], limit=1))
    environment_id = fields.Many2one('j_portainer.environment', string='Environment', required=True,
                                    default=lambda self: self.env['j_portainer.environment'].search([], limit=1))
    last_sync = fields.Datetime('Last Synchronized', readonly=True)
    
    # Build functionality fields
    build_method = fields.Selection([
        ('web_editor', 'Web Editor'),
        ('upload', 'Upload'),
        ('url', 'URL')
    ], string='Build Method', required=True, default='web_editor')
    
    dockerfile_content = fields.Text('Dockerfile Content', 
                                   help='Define the content of the Dockerfile')
    dockerfile_upload = fields.Binary('Dockerfile Upload',
                                    help='You can upload a Dockerfile or a tar archive containing a Dockerfile from your computer. When using a tarball, the root folder will be used as the build context.')
    build_url = fields.Char('URL',
                           help='Specify the URL to a Dockerfile, a tarball or a public Git repository (suffixed by .git). When using a Git repository URL, build contexts can be specified as in the Docker documentation.')
    dockerfile_path = fields.Char('Dockerfile Path',
                                 help='Indicate the path to the Dockerfile within the tarball/repository (ignored when using a Dockerfile).')
    
    def _get_api(self):
        """Get API client"""
        return self.env['j_portainer.api']
    
    @api.depends('size', 'shared_size', 'virtual_size')
    def _compute_formatted_sizes(self):
        """
        Format image sizes using decimal conversion (1000-based) to match Portainer display
        Converts raw byte values to human-readable format (B, KB, MB, GB)
        """
        for image in self:
            image.size_formatted = self._format_size_decimal(image.size)
            image.shared_size_formatted = self._format_size_decimal(image.shared_size)
            image.virtual_size_formatted = self._format_size_decimal(image.virtual_size)
    
    def _format_size_decimal(self, size_bytes):
        """
        Format size in bytes to human-readable format using decimal conversion (1000-based)
        This matches Portainer's size display exactly
        
        Args:
            size_bytes (float): Size in bytes
            
        Returns:
            str: Formatted size string (e.g., "129.9 MB", "116.5 MB")
        """
        if not size_bytes or size_bytes == 0:
            return "0 B"
        
        # Use decimal conversion (1000-based) to match Portainer
        if size_bytes < 1000:
            return f"{int(size_bytes)} B"
        elif size_bytes < 1000 * 1000:
            return f"{size_bytes / 1000:.1f} KB"
        elif size_bytes < 1000 * 1000 * 1000:
            return f"{size_bytes / (1000 * 1000):.1f} MB"
        else:
            return f"{size_bytes / (1000 * 1000 * 1000):.1f} GB"
    
    @api.onchange('build_method')
    def _onchange_build_method(self):
        """Clear irrelevant build fields when build method changes"""
        if self.build_method == 'web_editor':
            # Clear upload and URL fields
            self.dockerfile_upload = False
            self.build_url = False
            self.dockerfile_path = False
        elif self.build_method == 'upload':
            # Clear web editor and URL fields
            self.dockerfile_content = False
            self.build_url = False
            self.dockerfile_path = False
        elif self.build_method == 'url':
            # Clear web editor and upload fields
            self.dockerfile_content = False
            self.dockerfile_upload = False
    
    @api.model_create_multi
    def create(self, vals_list):
        """Override create to build image in Portainer before saving"""
        for vals in vals_list:
            # Only build in Portainer if this is a new image (no image_id yet)
            if not vals.get('image_id'):
                server_id = vals.get('server_id')
                environment_id = vals.get('environment_id')
                
                if not server_id or not environment_id:
                    raise UserError(_("Server and Environment are required to create an image"))
                
                # Get environment record to extract environment_id for API call
                env_record = self.env['j_portainer.environment'].browse(environment_id)
                if not env_record.exists():
                    raise UserError(_("Environment not found"))
                
                # Prepare build data
                build_data = {
                    'build_method': vals.get('build_method'),
                    'repository': vals.get('repository'),
                    'tag': vals.get('tag', 'latest'),
                    'dockerfile_content': vals.get('dockerfile_content'),
                    'dockerfile_upload': vals.get('dockerfile_upload'),
                    'build_url': vals.get('build_url'),
                    'dockerfile_path': vals.get('dockerfile_path')
                }
                
                # Build image in Portainer
                api = self.env['j_portainer.api']
                try:
                    build_result = api.build_image(server_id, env_record.environment_id, build_data)
                    
                    # Update vals with complete Portainer response data
                    vals.update({
                        'image_id': build_result.get('image_id'),
                        'created': build_result.get('created'),
                        'size': build_result.get('size', 0),
                        'shared_size': build_result.get('shared_size', 0),
                        'virtual_size': build_result.get('virtual_size', 0),
                        'labels': json.dumps(build_result.get('labels', {})) if build_result.get('labels') else None,
                        'details': build_result.get('details'),
                        'enhanced_layers_data': build_result.get('enhanced_layers_data'),
                        'last_sync': fields.Datetime.now()
                    })
                    
                    # Check if image with same image_id already exists in this environment
                    existing_image = self.search([
                        ('image_id', '=', vals['image_id']),
                        ('environment_id', '=', vals['environment_id'])
                    ], limit=1)
                    
                    if existing_image:
                        # Image already exists, add new tag to existing image
                        _logger.info(f"Image {vals['image_id']} already exists, adding tag {vals['repository']}:{vals['tag']}")
                        
                        # Create the new tag record for this repository:tag combination
                        existing_tag = self.env['j_portainer.image.tag'].search([
                            ('image_id', '=', existing_image.id),
                            ('repository', '=', vals['repository']),
                            ('tag', '=', vals['tag'])
                        ], limit=1)
                        
                        if not existing_tag:
                            _logger.info(f"Adding new tag {vals['repository']}:{vals['tag']} to existing image {existing_image.image_id}")
                            
                            # Update all_tags JSON field to include the new tag
                            current_tags = []
                            if existing_image.all_tags:
                                try:
                                    current_tags = json.loads(existing_image.all_tags)
                                except:
                                    current_tags = []
                            
                            # Add the new tag to the list
                            new_tag_info = {
                                'repository': vals['repository'],
                                'tag': vals['tag']
                            }
                            
                            # Check if this tag combination already exists in all_tags
                            tag_exists = any(
                                tag.get('repository') == vals['repository'] and tag.get('tag') == vals['tag']
                                for tag in current_tags
                            )
                            
                            if not tag_exists:
                                current_tags.append(new_tag_info)
                                existing_image.all_tags = json.dumps(current_tags)
                                _logger.info(f"Updated all_tags JSON with new tag: {vals['repository']}:{vals['tag']}")
                        
                        # Update existing image with latest data
                        existing_image.write({
                            'created': vals.get('created'),
                            'size': vals.get('size', 0),
                            'shared_size': vals.get('shared_size', 0),
                            'virtual_size': vals.get('virtual_size', 0),
                            'labels': vals.get('labels'),
                            'details': vals.get('details'),
                            'enhanced_layers_data': vals.get('enhanced_layers_data'),
                            'last_sync': fields.Datetime.now()
                        })
                        
                        # Force refresh of tag-related computed fields after update
                        
                        # Sync tags for existing image to include all current tags
                        existing_image._sync_image_tags()
                        
                        # Mark this vals as handled by setting a flag
                        vals['_duplicate_handled'] = True
                        vals['_existing_record'] = existing_image
                    
                except Exception as e:
                    # Prevent record creation if Portainer build fails
                    raise UserError(_("Failed to create image in Portainer: %s") % str(e))
        
        # Filter out duplicate-handled vals and collect existing records
        result_records = self.env['j_portainer.image']
        vals_to_create = []
        
        for vals in vals_list:
            if vals.get('_duplicate_handled'):
                # Add existing record to result
                result_records += vals['_existing_record']
                # Clean up temporary flags
                del vals['_duplicate_handled']
                del vals['_existing_record']
            else:
                vals_to_create.append(vals)
        
        # Create new records only for non-duplicate images
        if vals_to_create:
            new_records = super().create(vals_to_create)
            result_records += new_records
            
            # Add tag to all_tags JSON and sync for newly created images
            for record in new_records:
                # Create the all_tags JSON with the initial tag
                new_tag_info = {
                    'repository': record.repository,
                    'tag': record.tag
                }
                record.all_tags = json.dumps([new_tag_info])
                
                # Sync image tags to create the tag record immediately (skip during sync operations)
                if not self.env.context.get('sync_operation'):
                    record._sync_image_tags()
        
        return result_records
    
    @api.depends('repository', 'tag')
    def _compute_display_name(self):
        """Compute display name based on repository and tag"""
        for image in self:
            if image.tag:
                image.display_name = f"{image.repository}:{image.tag}"
            else:
                image.display_name = image.repository
                

    
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
                
                # Get current existing tags for this image
                existing_tags = image.image_tag_ids
                existing_tag_combinations = set()
                for tag in existing_tags:
                    existing_tag_combinations.add((tag.repository, tag.tag))
                
                # Find tags that should exist according to all_tags JSON
                expected_tag_combinations = set()
                tag_vals_list = []
                
                for tag_info in all_tags_data:
                    if isinstance(tag_info, dict) and 'repository' in tag_info and 'tag' in tag_info:
                        repo = tag_info['repository']
                        tag_name = tag_info['tag']
                        expected_tag_combinations.add((repo, tag_name))
                        
                        # Only add to creation list if it doesn't exist
                        if (repo, tag_name) not in existing_tag_combinations:
                            tag_vals_list.append({
                                'repository': repo,
                                'tag': tag_name,
                                'image_id': image.id
                            })
                
                # Create only missing tags with sync context to skip API calls
                if tag_vals_list:
                    # Mark these as sync mode to prevent API calls to Portainer
                    for tag_vals in tag_vals_list:
                        tag_vals['_sync_mode'] = True
                    self.env['j_portainer.image.tag'].create(tag_vals_list)
                    _logger.info(f"Created {len(tag_vals_list)} new tag records for image {image.image_id}")
                
                # Remove tags that shouldn't exist anymore
                tags_to_remove = existing_tags.filtered(
                    lambda t: (t.repository, t.tag) not in expected_tag_combinations
                )
                if tags_to_remove:
                    tags_to_remove.unlink()
                    _logger.info(f"Removed {len(tags_to_remove)} obsolete tag records for image {image.image_id}")
                    
            except Exception as e:
                _logger.error(f"Error syncing image tags for image {image.id}: {str(e)}")
                
    @api.depends('details', 'enhanced_layers_data')
    def _compute_layers(self):
        """Compute HTML formatted layers for this image
        Format: Order | Size | Layer Command
        Starting with Order 0 to match Portainer's display
        Uses enhanced layer data from Docker Image History API when available
        """
        for image in self:
            try:
                # First, try to use enhanced layer data from Image History API
                if image.enhanced_layers_data:
                    try:
                        _logger.info(f"Parsing enhanced layer data for image {image.repository}:{image.tag}")
                        _logger.debug(f"Enhanced layer data content: {image.enhanced_layers_data[:200]}...")
                        
                        enhanced_layers = json.loads(image.enhanced_layers_data)
                        
                        # Validate the parsed data structure
                        if not isinstance(enhanced_layers, list):
                            _logger.error(f"Enhanced layers data is not a list for {image.repository}:{image.tag}, got {type(enhanced_layers)}")
                            _logger.debug(f"Data: {enhanced_layers}")
                        elif not enhanced_layers:
                            _logger.warning(f"Enhanced layers data is empty for {image.repository}:{image.tag}")
                        else:
                            # Validate each layer object
                            valid_layers = []
                            for i, layer in enumerate(enhanced_layers):
                                if not isinstance(layer, dict):
                                    _logger.error(f"Layer {i} is not a dict for {image.repository}:{image.tag}, got {type(layer)}: {layer}")
                                    continue
                                
                                # Ensure required fields exist with safe defaults
                                safe_layer = {
                                    'command': str(layer.get('command', 'Unknown command')),
                                    'size': int(layer.get('size', 0)) if layer.get('size') is not None else 0,
                                    'created': str(layer.get('created', '')),
                                    'hash': str(layer.get('hash', '')),
                                    'empty_layer': bool(layer.get('empty_layer', False))
                                }
                                valid_layers.append(safe_layer)
                            
                            if valid_layers:
                                _logger.info(f"Using {len(valid_layers)} valid enhanced layers for image {image.repository}:{image.tag}")
                                image._format_enhanced_layers(valid_layers)
                                continue
                            else:
                                _logger.warning(f"No valid layers found in enhanced data for {image.repository}:{image.tag}")
                                
                    except (json.JSONDecodeError, TypeError, ValueError) as e:
                        _logger.error(f"Failed to parse enhanced layers for {image.repository}:{image.tag}: {str(e)}")
                        _logger.debug(f"Problematic data: {image.enhanced_layers_data}")
                    except Exception as e:
                        _logger.error(f"Unexpected error processing enhanced layers for {image.repository}:{image.tag}: {str(e)}")
                        _logger.debug(f"Data: {image.enhanced_layers_data}")
                
                # Fallback to legacy layer processing from details field
                if not image.details:
                    image.layers = "<div class='text-muted'>No layer information available</div>"
                    continue
                    
                details = json.loads(image.details)
                
                # Extract layers information using legacy method
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
    
    def _format_enhanced_layers(self, enhanced_layers):
        """
        Format enhanced layer data from Docker Image History API into HTML table
        Matches Portainer's exact display format and ordering
        
        Args:
            enhanced_layers (list): List of layer objects with command, size, created, hash
        """
        # Reverse the layer order to match Portainer (newest first, oldest last)
        reversed_layers = list(reversed(enhanced_layers))
        
        # Build HTML table for enhanced layers (matching Portainer layout)
        html = [
            '<table class="table table-sm table-striped">',
            '<thead>',
            '<tr>',
            '<th style="width: 60px;">#</th>',
            '<th style="width: 100px;">Size</th>',
            '<th>Layer</th>',
            '</tr>',
            '</thead>',
            '<tbody>'
        ]
        
        for i, layer in enumerate(reversed_layers):
            # Format size for display using decimal conversion (1000-based) to match Portainer
            size = layer.get('size', 0)
            if size == 0:
                size_str = '<span class="text-muted">0 B</span>'
            elif size < 1000:
                size_str = f"{size} B"
            elif size < 1000 * 1000:
                size_str = f"{size / 1000:.1f} KB"
            elif size < 1000 * 1000 * 1000:
                size_str = f"{size / (1000 * 1000):.1f} MB"
            else:
                size_str = f"{size / (1000 * 1000 * 1000):.1f} GB"
            
            # Get command and apply additional cleaning to match Portainer
            command = layer.get('command', 'Unknown command')
            
            # Apply the same advanced command cleaning used in API processing
            command = self.env['j_portainer.api']._clean_docker_command(command)
            
            # Don't truncate long commands - show full text with proper wrapping
            # Add title attribute for tooltip on hover
            
            # Mark empty layers with different styling
            row_class = 'text-muted' if layer.get('empty_layer', False) else ''
            
            html.append(f'<tr class="{row_class}">')
            html.append(f'<td>{i}</td>')
            html.append(f'<td>{size_str}</td>')
            html.append(f'<td class="text-monospace small" style="word-break: break-all; white-space: normal;" title="{command}">{command}</td>')
            html.append('</tr>')
        
        html.extend(['</tbody>', '</table>'])
        self.layers = ''.join(html)
    
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
    
    @api.depends('details')
    def _compute_env_html(self):
        """Compute HTML formatted table of environment variables"""
        for image in self:
            if not image.details:
                image.env_html = "<div class='text-muted'>No environment variables available</div>"
                continue
                
            try:
                details_data = json.loads(image.details)
                
                # Extract environment variables from Config.Env
                env_vars = []
                config = details_data.get('Config', {})
                if config and 'Env' in config and isinstance(config['Env'], list):
                    env_vars = config['Env']
                
                if not env_vars:
                    image.env_html = "<div class='text-muted'>No environment variables available</div>"
                    continue
                    
                # Generate HTML table for environment variables
                html = ['<table class="table table-sm table-bordered table-striped">',
                        '<thead>',
                        '<tr>',
                        '<th width="30%">Variable Name</th>',
                        '<th width="70%">Variable Value</th>',
                        '</tr>',
                        '</thead>',
                        '<tbody>']
                
                for env_var in sorted(env_vars):
                    # Parse environment variable (format: KEY=VALUE)
                    if '=' in env_var:
                        key, value = env_var.split('=', 1)
                    else:
                        key = env_var
                        value = ''
                    
                    # Escape HTML characters to prevent XSS
                    safe_key = str(key).replace('<', '&lt;').replace('>', '&gt;')
                    safe_value = str(value).replace('<', '&lt;').replace('>', '&gt;')
                    
                    html.append('<tr>')
                    html.append(f'<td class="text-monospace font-weight-bold">{safe_key}</td>')
                    html.append(f'<td class="text-monospace">{safe_value}</td>')
                    html.append('</tr>')
                    
                html.append('</tbody>')
                html.append('</table>')
                
                image.env_html = ''.join(html)
            except Exception as e:
                _logger.error(f"Error computing environment variables HTML for image {image.id}: {str(e)}")
                image.env_html = f"<div class='text-danger'>Error computing environment variables: {str(e)}</div>"
    
    @api.depends('details')
    def _compute_build_info(self):
        """Compute Docker build information like Portainer displays"""
        for image in self:
            if not image.details:
                image.build_info = "No build information available"
                continue
                
            try:
                details_data = json.loads(image.details)
                
                # Extract build information from Docker Engine details
                docker_version = details_data.get('DockerVersion', '')
                os_info = details_data.get('Os', '')
                architecture = details_data.get('Architecture', '')
                
                # Build the info string like Portainer: "Docker 28.1.1 on linux, amd64"
                build_parts = []
                
                if docker_version:
                    build_parts.append(f"Docker {docker_version}")
                
                if os_info and architecture:
                    build_parts.append(f"on {os_info}, {architecture}")
                elif os_info:
                    build_parts.append(f"on {os_info}")
                elif architecture:
                    build_parts.append(f"on {architecture}")
                
                if build_parts:
                    image.build_info = " ".join(build_parts)
                else:
                    image.build_info = "Build information not available"
                    
            except Exception as e:
                _logger.error(f"Error computing build info for image {image.id}: {str(e)}")
                image.build_info = f"Error computing build information: {str(e)}"
    
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
                endpoint=f"/endpoints/{self.environment_id.environment_id}/docker/images/{self.image_id}",
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