#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


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
        string='Repository Name',
        required=True,
        tracking=True,
        help='Name of the GitHub repository'
    )
    
    gr_external_id = fields.Char(
        string='External ID',
        required=True,
        tracking=True,
        help='External repository ID from GitHub Sync Server'
    )
    
    gr_url = fields.Char(
        string='Repository URL',
        tracking=True,
        help='URL of the GitHub repository'
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
        help='Whether this repository is active'
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
    
    def sync_repository(self):
        """Manually sync this repository."""
        self.ensure_one()
        try:
            result = self.gr_server_id._make_request('POST', f'repositories/{self.gr_external_id}/sync')
            if result and result.get('success'):
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
                raise UserError(_('Failed to sync repository: %s') % result.get('message', 'Unknown error'))
                
        except Exception as e:
            raise UserError(_('Sync failed: %s') % str(e))
    
    def action_open_repository(self):
        """Open repository in GitHub."""
        self.ensure_one()
        if self.gr_url:
            return {
                'type': 'ir.actions.act_url',
                'url': self.gr_url,
                'target': 'new',
            }
        else:
            raise UserError(_('No URL available for this repository'))