#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError


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
                    # Update status to success and set current time as last_pull
                    # Note: Actual last_pull time should come from next repository sync
                    self.write({
                        'gr_status': 'success',
                        'gr_last_pull': fields.Datetime.now()
                    })
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
    

    
    def action_delete_repository(self):
        """Delete repository with confirmation."""
        self.ensure_one()
        try:
            if self.gr_external_id:
                result = self.gr_server_id._make_request('DELETE', f'repositories/{self.gr_external_id}')
                if not (result and result.get('success')):
                    raise UserError(_('Failed to delete repository from server: %s') % result.get('message', 'Unknown error'))
            
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
    
