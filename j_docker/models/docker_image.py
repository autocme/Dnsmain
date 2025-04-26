import json
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

class DockerImage(models.Model):
    _name = 'docker.image'
    _description = 'Docker Image'
    _order = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Name', required=True, tracking=True,
                     help="Name of the Docker image (repository:tag)")
    
    docker_id = fields.Char(string='Image ID', tracking=True, readonly=True,
                          help="Docker image ID")
    
    server_id = fields.Many2one('docker.server', string='Server', required=True,
                              ondelete='cascade', tracking=True,
                              help="Server where this image is stored")
    
    active = fields.Boolean(default=True, tracking=True)
    
    # Image details
    repository = fields.Char(string='Repository', tracking=True,
                           help="Image repository name")
    
    tag = fields.Char(string='Tag', tracking=True,
                    help="Image tag")
    
    size = fields.Char(string='Size', readonly=True,
                     help="Size of the image")
    
    size_bytes = fields.Integer(string='Size (bytes)', readonly=True)
    
    created_at = fields.Char(string='Created At', readonly=True)
    
    created_date = fields.Datetime(string='Creation Date', readonly=True,
                                 compute='_compute_created_date', store=True)
    
    # Status & details
    digest = fields.Char(string='Digest', readonly=True,
                       help="Content-addressable identifier")
    
    architecture = fields.Char(string='Architecture', readonly=True)
    os = fields.Char(string='OS', readonly=True)
    
    labels = fields.Text(string='Labels', readonly=True)
    
    used_by_containers = fields.Integer(string='Used By Containers', 
                                      compute='_compute_used_by_containers')
    
    dangling = fields.Boolean(string='Dangling', 
                            compute='_compute_dangling',
                            store=True,
                            help="Image is not tagged and not used by any container")
    
    last_updated = fields.Datetime(string='Last Updated', readonly=True)
    notes = fields.Text(string='Notes')
    
    # Related logs
    log_ids = fields.One2many('docker.logs', 'image_id', string='Logs')
    
    # -------------------------------------------------------------------------
    # Compute methods
    # -------------------------------------------------------------------------
    @api.depends('created_at')
    def _compute_created_date(self):
        for image in self:
            if image.created_at:
                try:
                    # Try to parse the timestamp - this is a simplified approach
                    # Actual implementation might need handling different formats
                    # from different Docker versions
                    created_at = image.created_at.strip()
                    if 'ago' in created_at:
                        # Current implementation doesn't handle "X days ago" format well
                        # Real implementation would need more sophisticated parsing
                        image.created_date = fields.Datetime.now()
                    else:
                        image.created_date = fields.Datetime.from_string(created_at)
                except Exception as e:
                    _logger.warning(f"Could not parse image creation date: {e}")
                    image.created_date = False
            else:
                image.created_date = False
    
    def _compute_used_by_containers(self):
        for image in self:
            # Count containers using this image
            containers = self.env['docker.container'].search_count([
                ('server_id', '=', image.server_id.id),
                ('image', 'ilike', image.name),
                ('active', '=', True)
            ])
            image.used_by_containers = containers
    
    @api.depends('tag', 'used_by_containers')
    def _compute_dangling(self):
        for image in self:
            image.dangling = (not image.tag or image.tag == '<none>') and image.used_by_containers == 0
    
    # -------------------------------------------------------------------------
    # Action methods
    # -------------------------------------------------------------------------
    def action_refresh(self):
        """Refresh image details"""
        self.ensure_one()
        self._update_image_details()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Image Refresh'),
                'message': _('Image details updated for %s') % self.name,
                'type': 'info',
                'sticky': False,
            }
        }
    
    def action_remove(self):
        """Remove the image"""
        self.ensure_one()
        
        if self.used_by_containers > 0:
            raise UserError(_('Cannot remove image that is being used by containers.'))
        
        try:
            server = self.server_id
            ssh_client = server.ssh_client_id
            
            if not ssh_client:
                raise UserError(_('No SSH client configured for server %s') % server.name)
            
            # Check if using image ID is safer
            img_reference = self.docker_id if self.docker_id else self.name
            
            cmd = f"docker rmi {img_reference}"
            result = ssh_client.exec_command(cmd)
            
            # Check if the command was successful (usually returns the image ID/name that was removed)
            if self.docker_id in result or self.name in result:
                self.active = False
                self.last_updated = fields.Datetime.now()
                self._create_log_entry('info', 'Image removed')
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Image Removed'),
                        'message': _('Image %s removed successfully') % self.name,
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                self._create_log_entry('error', f'Failed to remove image: {result}')
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Error'),
                        'message': _('Failed to remove image. See logs for details.'),
                        'type': 'warning',
                        'sticky': False,
                    }
                }
                
        except Exception as e:
            self._create_log_entry('error', f'Error removing image: {str(e)}')
            raise UserError(_('Error removing image: %s') % str(e))
    
    def action_pull(self):
        """Open wizard to pull latest version of this image"""
        self.ensure_one()
        return {
            'name': _('Pull Image'),
            'type': 'ir.actions.act_window',
            'res_model': 'docker.pull.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_server_id': self.server_id.id,
                'default_image_name': self.name if ':' in self.name else f"{self.name}:latest"
            },
        }
    
    def action_inspect(self):
        """Inspect image details"""
        self.ensure_one()
        try:
            server = self.server_id
            ssh_client = server.ssh_client_id
            
            if not ssh_client:
                raise UserError(_('No SSH client configured for server %s') % server.name)
            
            img_reference = self.docker_id if self.docker_id else self.name
            cmd = f"docker inspect {img_reference}"
            result = ssh_client.exec_command(cmd)
            
            return {
                'name': _('Image Inspection'),
                'type': 'ir.actions.act_window',
                'res_model': 'docker.inspect.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_image_id': self.id,
                    'default_inspect_content': result
                },
            }
                
        except Exception as e:
            self._create_log_entry('error', f'Error inspecting image: {str(e)}')
            raise UserError(_('Error inspecting image: %s') % str(e))
    
    def action_create_container(self):
        """Open wizard to create a container from this image"""
        self.ensure_one()
        return {
            'name': _('Create Container'),
            'type': 'ir.actions.act_window',
            'res_model': 'docker.create.container.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_server_id': self.server_id.id,
                'default_image_id': self.id,
                'default_image_name': self.name
            },
        }
    
    def action_view_history(self):
        """View image history"""
        self.ensure_one()
        try:
            server = self.server_id
            ssh_client = server.ssh_client_id
            
            if not ssh_client:
                raise UserError(_('No SSH client configured for server %s') % server.name)
            
            img_reference = self.docker_id if self.docker_id else self.name
            cmd = f"docker history {img_reference} --no-trunc --format '{{{{json .}}}}'"
            result = ssh_client.exec_command(cmd)
            
            # Format the history output
            history_lines = []
            for line in result.strip().split('\n'):
                if not line:
                    continue
                try:
                    history_data = json.loads(line)
                    created_by = history_data.get('CreatedBy', '').replace('/bin/sh -c #(nop) ', '').replace('/bin/sh -c', 'RUN')
                    size = history_data.get('Size', '0')
                    comment = history_data.get('Comment', '')
                    
                    history_line = f"{created_by} ({size})"
                    if comment:
                        history_line += f" # {comment}"
                    
                    history_lines.append(history_line)
                except json.JSONDecodeError:
                    history_lines.append(line)
            
            formatted_history = '\n'.join(history_lines)
            
            return {
                'name': _('Image History'),
                'type': 'ir.actions.act_window',
                'res_model': 'docker.history.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_image_id': self.id,
                    'default_history_content': formatted_history
                },
            }
                
        except Exception as e:
            self._create_log_entry('error', f'Error viewing image history: {str(e)}')
            raise UserError(_('Error viewing image history: %s') % str(e))
    
    # -------------------------------------------------------------------------
    # Helper methods for image interaction
    # -------------------------------------------------------------------------
    def _update_image_details(self):
        """Update image details from Docker"""
        self.ensure_one()
        
        try:
            server = self.server_id
            ssh_client = server.ssh_client_id
            
            if not ssh_client:
                return False
            
            # Get image details
            img_reference = self.docker_id if self.docker_id else self.name
            cmd = f"docker inspect {img_reference} --format '{{{{json .}}}}'"
            result = ssh_client.exec_command(cmd)
            
            try:
                if result and '{' in result:
                    image_details = json.loads(result)
                    
                    if isinstance(image_details, list) and image_details:
                        details = image_details[0]
                        
                        # Extract digest
                        repo_digests = details.get('RepoDigests', [])
                        if repo_digests and isinstance(repo_digests, list) and len(repo_digests) > 0:
                            # Get the digest part after the @
                            digest_parts = repo_digests[0].split('@')
                            if len(digest_parts) > 1:
                                self.digest = digest_parts[1]
                        
                        # Extract architecture and OS
                        self.architecture = details.get('Architecture', '')
                        self.os = details.get('Os', '')
                        
                        # Extract size in bytes
                        self.size_bytes = details.get('Size', 0)
                        
                        # Extract labels
                        config = details.get('Config', {})
                        labels = config.get('Labels', {})
                        if labels:
                            labels_info = []
                            for key, value in labels.items():
                                labels_info.append(f"{key}={value}")
                            
                            if labels_info:
                                self.labels = '\n'.join(labels_info)
                        
                        self.last_updated = fields.Datetime.now()
                        self._create_log_entry('info', 'Image details updated')
                        return True
                        
            except json.JSONDecodeError as json_err:
                self._create_log_entry('error', f'Error parsing image details: {str(json_err)}')
            except Exception as e:
                self._create_log_entry('error', f'Error updating image details: {str(e)}')
            
            return False
                
        except Exception as e:
            self._create_log_entry('error', f'Error fetching image details: {str(e)}')
            return False
    
    def _create_log_entry(self, level, message):
        """Create a log entry for the image"""
        self.ensure_one()
        
        self.env['docker.logs'].create({
            'server_id': self.server_id.id,
            'image_id': self.id,
            'level': level,
            'name': message,
            'user_id': self.env.user.id,
        })