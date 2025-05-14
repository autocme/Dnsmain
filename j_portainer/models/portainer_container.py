#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import json
import logging

_logger = logging.getLogger(__name__)

class PortainerContainer(models.Model):
    _name = 'j_portainer.container'
    _description = 'Portainer Container'
    _order = 'name'
    
    name = fields.Char('Name', required=True)
    container_id = fields.Char('Container ID', required=True)
    image = fields.Char('Image', required=True)
    image_id = fields.Char('Image ID')
    created = fields.Datetime('Created')
    status = fields.Char('Status')
    state = fields.Selection([
        ('running', 'Running'),
        ('stopped', 'Stopped'),
        ('paused', 'Paused'),
        ('exited', 'Exited'),
        ('restarting', 'Restarting'),
        ('dead', 'Dead'),
        ('created', 'Created'),
    ], string='State', default='created')
    ports = fields.Text('Ports')
    labels = fields.Text('Labels')
    details = fields.Text('Details')
    volumes = fields.Text('Volumes')
    get_formatted_volumes = fields.Html('Formatted Volumes', compute='_compute_formatted_volumes')
    get_formatted_ports = fields.Html('Formatted Ports', compute='_compute_formatted_ports')
    
    server_id = fields.Many2one('j_portainer.server', string='Server', required=True, ondelete='cascade')
    environment_id = fields.Integer('Environment ID', required=True)
    environment_name = fields.Char('Environment', required=True)
    
    # One2many relationship to container labels
    label_ids = fields.One2many('j_portainer.container.label', 'container_id', string='Container Labels')
    
    def _get_api(self):
        """Get API client"""
        return self.env['j_portainer.api']
    
    def get_formatted_labels(self):
        """Get formatted container labels"""
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
            
    @api.depends('ports')
    def _compute_formatted_ports(self):
        """Compute formatted port mappings HTML table"""
        for record in self:
            if not record.ports:
                record.get_formatted_ports = '<p>No port mappings for this container</p>'
                continue
                
            try:
                ports_data = json.loads(record.ports)
                if not ports_data:
                    record.get_formatted_ports = '<p>No port mappings for this container</p>'
                    continue
                    
                html = ['<table class="table table-sm table-hover">',
                        '<thead>',
                        '<tr>',
                        '<th>Host IP</th>',
                        '<th>Host Port</th>',
                        '<th>Container Port</th>',
                        '<th>Protocol</th>',
                        '</tr>',
                        '</thead>',
                        '<tbody>']
                        
                for port in ports_data:
                    # Extract port mapping data
                    host_ip = port.get('IP', '0.0.0.0')
                    host_port = port.get('PublicPort', '-')
                    container_port = port.get('PrivatePort', '-')
                    protocol = port.get('Type', 'tcp')
                    
                    # Create a row for this port mapping
                    html.append('<tr>')
                    html.append(f'<td>{host_ip}</td>')
                    html.append(f'<td>{host_port}</td>')
                    html.append(f'<td>{container_port}</td>')
                    html.append(f'<td>{protocol}</td>')
                    html.append('</tr>')
                    
                html.append('</tbody>')
                html.append('</table>')
                
                record.get_formatted_ports = ''.join(html)
            except Exception as e:
                _logger.error(f"Error formatting ports for container {record.name}: {str(e)}")
                record.get_formatted_ports = f'<p>Error formatting ports: {str(e)}</p>'
    
    @api.depends('volumes')
    def _compute_formatted_volumes(self):
        """Compute formatted container volumes HTML"""
        for record in self:
            if not record.volumes:
                record.get_formatted_volumes = '<p>No volumes attached to this container</p>'
                continue
                
            try:
                volumes_data = json.loads(record.volumes)
                if not volumes_data:
                    record.get_formatted_volumes = '<p>No volumes attached to this container</p>'
                    continue
                    
                html = ['<table class="table table-sm table-hover">',
                        '<thead>',
                        '<tr>',
                        '<th>Type</th>',
                        '<th>Name/Source</th>',
                        '<th>Container Path</th>',
                        '<th>Mode</th>',
                        '</tr>',
                        '</thead>',
                        '<tbody>']
                        
                for volume in volumes_data:
                    # Determine volume type
                    source = volume.get('Source', '')
                    if '/var/lib/docker/volumes/' in source:
                        # This is a named volume
                        volume_name = source.split('/var/lib/docker/volumes/')[1].split('/_data')[0]
                        volume_type = 'Named Volume'
                    elif source.startswith('/'):
                        # This is a bind mount
                        volume_name = source
                        volume_type = 'Bind Mount'
                    else:
                        # This is probably a tmpfs or other type
                        volume_name = source if source else 'N/A'
                        volume_type = 'Other'
                        
                    destination = volume.get('Destination', 'N/A')
                    mode = volume.get('Mode', 'N/A')
                    
                    # Create a row for this volume
                    html.append('<tr>')
                    html.append(f'<td>{volume_type}</td>')
                    html.append(f'<td>{volume_name}</td>')
                    html.append(f'<td>{destination}</td>')
                    html.append(f'<td>{mode}</td>')
                    html.append('</tr>')
                    
                html.append('</tbody>')
                html.append('</table>')
                
                record.get_formatted_volumes = ''.join(html)
            except Exception as e:
                _logger.error(f"Error formatting volumes for container {record.name}: {str(e)}")
                record.get_formatted_volumes = f'<p>Error formatting volumes: {str(e)}</p>'
    
    def get_state_color(self):
        """Get color for container state"""
        self.ensure_one()
        colors = {
            'running': 'success',
            'stopped': 'danger',
            'paused': 'warning',
            'exited': 'danger',
            'restarting': 'info',
            'dead': 'danger',
            'created': 'secondary'
        }
        return colors.get(self.state, 'secondary')
    
    def start(self):
        """Start the container"""
        self.ensure_one()
        
        try:
            api = self._get_api()
            result = api.container_action(
                self.server_id.id, self.environment_id, self.container_id, 'start')

            if result:
                # Update container state
                self.write({'state': 'running', 'status': 'Up'})
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Container Started'),
                        'message': _('Container %s started successfully') % self.name,
                        'sticky': False,
                        'type': 'success',
                    }
                }
            else:
                raise UserError(_("Failed to start container"))
        except Exception as e:
            _logger.error(f"Error starting container {self.name}: {str(e)}")
            raise UserError(_("Error starting container: %s") % str(e))
    
    def stop(self):
        """Stop the container"""
        self.ensure_one()
        
        try:
            api = self._get_api()
            result = api.container_action(
                self.server_id.id, self.environment_id, self.container_id, 'stop')
                
            if result:
                # Update container state
                self.write({'state': 'stopped', 'status': 'Stopped'})
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Container Stopped'),
                        'message': _('Container %s stopped successfully') % self.name,
                        'sticky': False,
                        'type': 'success',
                    }
                }
            else:
                raise UserError(_("Failed to stop container"))
        except Exception as e:
            _logger.error(f"Error stopping container {self.name}: {str(e)}")
            raise UserError(_("Error stopping container: %s") % str(e))
    
    def restart(self):
        """Restart the container"""
        self.ensure_one()
        
        try:
            api = self._get_api()
            result = api.container_action(
                self.server_id.id, self.environment_id, self.container_id, 'restart')
                
            if result:
                # Update container state
                self.write({'state': 'running', 'status': 'Up'})
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Container Restarted'),
                        'message': _('Container %s restarted successfully') % self.name,
                        'sticky': False,
                        'type': 'success',
                    }
                }
            else:
                raise UserError(_("Failed to restart container"))
        except Exception as e:
            _logger.error(f"Error restarting container {self.name}: {str(e)}")
            raise UserError(_("Error restarting container: %s") % str(e))
    
    def pause(self):
        """Pause the container"""
        self.ensure_one()
        
        try:
            api = self._get_api()
            result = api.container_action(
                self.server_id.id, self.environment_id, self.container_id, 'pause')
                
            if result:
                # Update container state
                self.write({'state': 'paused', 'status': 'Paused'})
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Container Paused'),
                        'message': _('Container %s paused successfully') % self.name,
                        'sticky': False,
                        'type': 'success',
                    }
                }
            else:
                raise UserError(_("Failed to pause container"))
        except Exception as e:
            _logger.error(f"Error pausing container {self.name}: {str(e)}")
            raise UserError(_("Error pausing container: %s") % str(e))
    
    def unpause(self):
        """Unpause the container"""
        self.ensure_one()
        
        try:
            api = self._get_api()
            result = api.container_action(
                self.server_id.id, self.environment_id, self.container_id, 'unpause')
                
            if result:
                # Update container state
                self.write({'state': 'running', 'status': 'Up'})
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Container Unpaused'),
                        'message': _('Container %s unpaused successfully') % self.name,
                        'sticky': False,
                        'type': 'success',
                    }
                }
            else:
                raise UserError(_("Failed to unpause container"))
        except Exception as e:
            _logger.error(f"Error unpausing container {self.name}: {str(e)}")
            raise UserError(_("Error unpausing container: %s") % str(e))
    
    def kill(self):
        """Kill the container"""
        self.ensure_one()
        
        try:
            api = self._get_api()
            result = api.container_action(
                self.server_id.id, self.environment_id, self.container_id, 'kill')
                
            if result:
                # Update container state
                self.write({'state': 'stopped', 'status': 'Killed'})
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Container Killed'),
                        'message': _('Container %s killed successfully') % self.name,
                        'sticky': False,
                        'type': 'success',
                    }
                }
            else:
                raise UserError(_("Failed to kill container"))
        except Exception as e:
            _logger.error(f"Error killing container {self.name}: {str(e)}")
            raise UserError(_("Error killing container: %s") % str(e))
    
    def remove(self, force=False, volumes=False):
        """Remove the container
        
        Args:
            force (bool): Force removal
            volumes (bool): Remove volumes associated with the container
            
        Returns:
            dict: Action result
            
        Raises:
            UserError: If container removal fails
        """
        self.ensure_one()
        
        try:
            api = self._get_api()
            result = api.remove_container(
                self.server_id.id, self.environment_id, self.container_id,
                force=force, volumes=volumes)
            
            if isinstance(result, dict) and 'success' in result:
                if result['success']:
                    # Delete the record
                    self.unlink()
                    self.env.cr.commit()

                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Container Removed'),
                            'message': _('Container %s removed successfully') % self.name,
                            'sticky': False,
                            'type': 'success',
                        }
                    }
                else:
                    # API returned failure with message
                    error_message = result.get('message', _("Failed to remove container"))
                    _logger.error(f"Failed to remove container {self.name}: {error_message}")
                    raise UserError(error_message)
            elif result:
                # Legacy boolean True result
                self.unlink()
                self.env.cr.commit()
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Container Removed'),
                        'message': _('Container %s removed successfully') % self.name,
                        'sticky': False,
                        'type': 'success',
                    }
                }
            else:
                # Legacy boolean False result
                raise UserError(_("Failed to remove container"))
        except Exception as e:
            _logger.error(f"Error removing container {self.name}: {str(e)}")
            raise UserError(_("Error removing container: %s") % str(e))
    
    def action_remove_with_options(self):
        """Action to show container removal options"""
        self.ensure_one()
        
        return {
            'name': _('Remove Container'),
            'type': 'ir.actions.act_window',
            'res_model': 'j_portainer.container.remove.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_container_id': self.id,
                'default_container_name': self.name,
            }
        }
    
    def action_refresh(self):
        """Refresh container information"""
        self.ensure_one()
        
        try:
            self.server_id.sync_containers(self.environment_id)
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Container Refreshed'),
                    'message': _('Container information refreshed successfully'),
                    'sticky': False,
                    'type': 'success',
                }
            }
        except Exception as e:
            _logger.error(f"Error refreshing container {self.name}: {str(e)}")
            raise UserError(_("Error refreshing container: %s") % str(e))
    
    def action_view_logs(self):
        """View container logs"""
        self.ensure_one()
        
        return {
            'name': _('Container Logs: %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'j_portainer.container.logs.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_id': self.id,
                'active_model': 'j_portainer.container',
            }
        }