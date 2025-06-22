#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class GitHubRepositoryEditWizard(models.TransientModel):
    """
    GitHub Repository Edit Wizard
    
    This wizard allows editing specific repository fields as shown in the UI.
    """
    
    _name = 'github.repository.edit.wizard'
    _description = 'GitHub Repository Edit Wizard'

    # ========================================================================
    # EDITABLE FIELDS
    # ========================================================================
    
    repository_id = fields.Many2one(
        'github.repository',
        string='Repository',
        required=True,
        ondelete='cascade'
    )
    
    gre_name = fields.Char(
        string='Repository Name',
        required=True,
        help='Name of the GitHub repository'
    )
    
    gre_url = fields.Char(
        string='Repository URL',
        required=True,
        help='URL of the GitHub repository'
    )
    
    gre_branch = fields.Char(
        string='Branch',
        required=True,
        help='Branch name for the repository'
    )
    
    gre_local_path = fields.Char(
        string='Local Path',
        required=True,
        help='Local storage path for the repository'
    )
    
    gre_active = fields.Boolean(
        string='Active',
        help='Repository will be synced when active'
    )

    # ========================================================================
    # ONCHANGE METHODS
    # ========================================================================
    
    @api.onchange('repository_id')
    def _onchange_repository_id(self):
        """Load repository data when repository is selected."""
        if self.repository_id:
            self.gre_name = self.repository_id.gr_name
            self.gre_url = self.repository_id.gr_url
            self.gre_branch = self.repository_id.gr_branch
            self.gre_local_path = self.repository_id.gr_local_path
            self.gre_active = self.repository_id.gr_active

    # ========================================================================
    # ACTION METHODS
    # ========================================================================
    
    def action_save_changes(self):
        """Save the changes to the repository."""
        self.ensure_one()
        if not self.repository_id:
            raise UserError(_('Repository not found'))
        
        # Update repository with new values
        self.repository_id.write({
            'gr_name': self.gre_name,
            'gr_url': self.gre_url,
            'gr_branch': self.gre_branch,
            'gr_local_path': self.gre_local_path,
            'gr_active': self.gre_active,
        })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': _('Repository updated successfully'),
                'type': 'success',
                'sticky': False,
            }
        }
    
    def action_cancel(self):
        """Cancel the edit operation."""
        return {'type': 'ir.actions.act_window_close'}