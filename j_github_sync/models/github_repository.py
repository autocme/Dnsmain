#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class GitHubRepository(models.Model):
    """
    GitHub Repository Model
    
    This model represents GitHub repositories synchronized from the GitHub Sync Server.
    """
    
    _name = 'github.repository'
    _description = 'GitHub Repository'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'gr_name'
    _rec_name = 'gr_name'

    # ========================================================================
    # BASIC FIELDS
    # ========================================================================
    
    gr_name = fields.Char(
        string='Name',
        required=True,
        tracking=True,
        help='Name of the GitHub repository'
    )
    
    gr_url = fields.Char(
        string='URL',
        required=True,
        tracking=True,
        help='URL of the GitHub repository'
    )
    
    gr_branch = fields.Char(
        string='Branch',
        default='main',
        tracking=True,
        help='Branch name for the repository'
    )
    
    gr_local_path = fields.Char(
        string='Local Path',
        tracking=True,
        help='Local storage path for the repository'
    )
    
    # Track fields that require server update
    _server_update_fields = ['gr_name', 'gr_url', 'gr_branch', 'gr_local_path']
    
    gr_status = fields.Selection([
        ('success', 'Success'),
        ('error', 'Error'),
        ('warning', 'Warning'),
        ('pending', 'Pending'),
        ('syncing', 'Syncing')
    ], string='Status', default='pending', tracking=True,
       help='Current status of the repository')
    
    gr_last_pull = fields.Datetime(
        string='Last Pull',
        tracking=True,
        help='Timestamp of the last pull operation'
    )
    
    gr_external_id = fields.Char(
        string='External ID',
        help='External repository ID from GitHub Sync Server'
    )
    
    gr_description = fields.Text(
        string='Description',
        tracking=True,
        help='Repository description'
    )
    
    gr_private = fields.Boolean(
        string='Private Repository',
        default=False,
        tracking=True,
        help='Whether this is a private repository'
    )
    
    gr_active = fields.Boolean(
        string='Active',
        default=True,
        tracking=True,
        help='Whether this repository is active (repository will be synced)'
    )
    
    # ========================================================================
    # RELATIONSHIPS
    # ========================================================================
    
    gr_server_id = fields.Many2one(
        'github.sync.server',
        string='GitHub Sync Server',
        required=True,
        ondelete='cascade',
        tracking=True,
        help='GitHub Sync Server that manages this repository'
    )
    
    gr_company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        tracking=True
    )

    # ========================================================================
    # CONSTRAINTS
    # ========================================================================
    
    _sql_constraints = [
        ('unique_external_id_server', 'UNIQUE(gr_external_id, gr_server_id)', 
         'Repository external ID must be unique per server.'),
    ]

    # ========================================================================
    # REPOSITORY OPERATIONS
    # ========================================================================
    
    def action_sync_repository(self):
        """Manually sync this repository."""
        self.ensure_one()
        try:
            self.write({'gr_status': 'syncing'})
            result = self.gr_server_id._make_request('POST', f'repositories/{self.gr_external_id}/sync')
            
            if result:
                # Handle different response formats
                success = False
                message = 'Unknown response'
                
                if isinstance(result, dict):
                    success = result.get('success', False)
                    message = result.get('message', 'Repository sync completed')
                elif isinstance(result, list):
                    success = True
                    message = 'Repository sync initiated'
                else:
                    success = True
                    message = 'Repository sync response received'
                
                if success:
                    # Extract last_pull_time from response - ONLY update if provided by server
                    update_vals = {'gr_status': 'success'}
                    
                    if isinstance(result, dict) and 'last_pull_time' in result:
                        last_pull_time = result['last_pull_time']
                        
                        # Only update gr_last_pull if server provides last_pull_time
                        if last_pull_time:
                            try:
                                from datetime import datetime, timedelta
                                # Handle ISO format with microseconds
                                if 'T' in last_pull_time:
                                    # Remove microseconds if present: 2025-06-23T10:49:36.900591
                                    if '.' in last_pull_time:
                                        last_pull_time = last_pull_time.split('.')[0]
                                    gr_last_pull = datetime.strptime(last_pull_time, '%Y-%m-%dT%H:%M:%S')
                                    update_vals['gr_last_pull'] = gr_last_pull
                                    _logger.info(f"Updated gr_last_pull from server response: {gr_last_pull}")
                            except (ValueError, TypeError) as e:
                                _logger.error(f"Failed to parse last_pull_time '{last_pull_time}': {e}")
                        elif last_pull_time is None:
                            # Server explicitly says no pull time - don't update the field
                            _logger.info("Server response has last_pull_time=None, keeping existing gr_last_pull")
                    else:
                        # No last_pull_time in response - don't update gr_last_pull field
                        _logger.info("No last_pull_time in server response, keeping existing gr_last_pull")
                    
                    self.write(update_vals)
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'message': _('Repository synced successfully'),
                            'type': 'success',
                            'sticky': False,
                        }
                    }
                else:
                    self.write({'gr_status': 'error'})
                    raise UserError(_('Failed to sync repository: %s') % message)
            else:
                self.write({'gr_status': 'error'})
                raise UserError(_('No response from sync server'))
                
        except Exception as e:
            self.write({'gr_status': 'error'})
            raise UserError(_('Sync failed: %s') % str(e))

    def action_create_repository(self):
        """Create this repository on the GitHub Sync Server."""
        self.ensure_one()
        
        if self.gr_external_id and self.gr_external_id != '0':
            raise UserError(_('Repository already exists on sync server'))
        
        if not self.gr_server_id:
            raise UserError(_('No sync server selected for this repository'))
        
        try:
            # Prepare repository data for creation
            repo_data = {
                'name': self.gr_name,
                'url': self.gr_url,
                'branch': self.gr_branch,
                'local_path': self.gr_local_path,
                'description': self.gr_description or '',
                'private': self.gr_private,
            }
            
            result = self.gr_server_id._make_request('POST', 'repositories', repo_data)
            
            if result and isinstance(result, dict):
                # Update repository with returned external ID and last_pull_time
                external_id = result.get('id') or result.get('external_id')
                last_pull_time = result.get('last_pull_time')
                
                if external_id:
                    # Parse last_pull_time if provided
                    gr_last_pull = None
                    if last_pull_time:
                        try:
                            from datetime import datetime, timedelta
                            # Handle ISO format with microseconds
                            if 'T' in last_pull_time:
                                # Remove microseconds if present: 2025-06-23T10:49:36.900591
                                if '.' in last_pull_time:
                                    last_pull_time = last_pull_time.split('.')[0]
                                gr_last_pull = datetime.strptime(last_pull_time, '%Y-%m-%dT%H:%M:%S')
                                # Adjust for server timezone offset (server is 3 hours ahead)
                                gr_last_pull = gr_last_pull - timedelta(hours=3)
                        except (ValueError, TypeError) as e:
                            _logger.error(f"Failed to parse last_pull_time '{last_pull_time}': {e}")
                            gr_last_pull = None
                    
                    # Determine status based on last_pull_time
                    status = 'success' if gr_last_pull else 'pending'
                    
                    self.write({
                        'gr_external_id': str(external_id),
                        'gr_status': status,
                        'gr_last_pull': gr_last_pull
                    })
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'message': _('Repository created successfully on sync server'),
                            'type': 'success',
                            'sticky': False,
                        }
                    }
                else:
                    raise UserError(_('Repository created but no external ID returned'))
            else:
                raise UserError(_('Failed to create repository on sync server'))
                
        except Exception as e:
            raise UserError(_('Error creating repository: %s') % str(e))
    
    def action_delete_repository(self):
        """Delete repository with confirmation."""
        self.ensure_one()
        try:
            if self.gr_external_id:
                result = self.gr_server_id._make_request('DELETE', f'repositories/{self.gr_external_id}')
                
                # Handle different response formats from server
                if result:
                    if isinstance(result, dict):
                        # Check for success field or success message
                        success = result.get('success', True)  # Default to True if no success field
                        message = result.get('message', 'Repository deleted from server')
                        
                        if not success and 'success' not in message.lower():
                            raise UserError(_('Failed to delete repository from server: %s') % message)
                    # If result is not a dict (e.g., string response), consider it successful
                else:
                    raise UserError(_('No response from server when deleting repository'))
            
            # If we reach here, deletion was successful, remove from Odoo
            self.unlink()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': _('Repository deleted successfully'),
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            raise UserError(_('Delete failed: %s') % str(e))
    
    def write(self, vals):
        """Override write to update server when specific fields change."""
        # Check if any server-update fields are being modified
        update_server_fields = set(vals.keys()) & set(self._server_update_fields)
        
        if update_server_fields and self.gr_external_id and self.gr_external_id != '0':
            _logger.info(f"Repository {self.gr_name} - Server update required for fields: {update_server_fields}")
            
            # Prepare update data for server
            update_data = {}
            if 'gr_name' in vals:
                update_data['name'] = vals['gr_name']
            if 'gr_url' in vals:
                update_data['url'] = vals['gr_url']
            if 'gr_branch' in vals:
                update_data['branch'] = vals['gr_branch']
            if 'gr_local_path' in vals:
                update_data['local_path'] = vals['gr_local_path']
            
            if update_data:
                _logger.info(f"Sending PUT request to server with data: {update_data}")
                try:
                    # Update repository on server using PUT method
                    result = self.gr_server_id._make_request('PUT', f'repositories/{self.gr_external_id}', data=update_data)
                    _logger.info(f"Server PUT response: {result}")
                    
                    if not result:
                        raise UserError(_('No response from server when updating repository'))
                    
                    # Check if update was successful
                    if isinstance(result, dict):
                        success = result.get('success', True)
                        message = result.get('message', 'Repository updated')
                        
                        # Log server response details
                        _logger.info(f"Server response - success: {success}, message: {message}")
                        
                        # Verify the update was actually applied by checking returned data
                        if 'gr_local_path' in vals and 'local_path' in result:
                            returned_path = result.get('local_path')
                            expected_path = vals['gr_local_path']
                            _logger.info(f"Local path verification - Expected: {expected_path}, Returned: {returned_path}")
                            
                            if returned_path != expected_path:
                                raise UserError(_('Server update failed: local_path was not updated. Expected: %s, Got: %s') % (expected_path, returned_path))
                        
                        if not success and 'success' not in message.lower():
                            raise UserError(_('Failed to update repository on server: %s') % message)
                    
                except Exception as e:
                    _logger.error(f"Server update failed: {e}")
                    raise UserError(_('Failed to update repository on server: %s') % str(e))
        
        # If server update successful or no server fields changed, proceed with local update
        return super().write(vals)
    
