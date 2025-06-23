#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)

class SyncConfigWizard(models.TransientModel):
    _name = 'j_github_sync.sync.config.wizard'
    _description = 'GitHub Sync Configuration Wizard'
    
    sync_period_days = fields.Integer(
        string='Sync Period (Days)',
        default=1,
        required=True,
        help="Number of days between automatic sync operations. The scheduled action will run every this period to sync repositories and logs."
    )
    
    @api.model
    def default_get(self, fields_list):
        """Get default values for the wizard"""
        res = super(SyncConfigWizard, self).default_get(fields_list)
        
        # Get current value from system parameters
        param_days = self.env['ir.config_parameter'].sudo().get_param('j_github_sync.sync_period_days', '1')
        try:
            days = int(param_days)
            if days < 1:
                days = 1
        except (ValueError, TypeError):
            days = 1
            
        res['sync_period_days'] = days
        return res
    
    @api.constrains('sync_period_days')
    def _check_sync_period_days(self):
        """Ensure sync period is a positive integer"""
        for record in self:
            if record.sync_period_days < 1:
                raise ValidationError(_("Sync period must be at least 1 day"))
    
    def save_config(self):
        """Save configuration to system parameters and update cron job"""
        self.ensure_one()
        
        # Update system parameter
        self.env['ir.config_parameter'].sudo().set_param('j_github_sync.sync_period_days', str(self.sync_period_days))
        
        # Update cron job interval
        cron_job = self.env.ref('j_github_sync.ir_cron_github_sync_repositories', raise_if_not_found=False)
        if cron_job:
            cron_job.write({
                'interval_number': self.sync_period_days,
                'interval_type': 'days'
            })
        
        # Show success message
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Configuration Saved'),
                'message': _('Sync period has been updated to %d day(s).') % self.sync_period_days,
                'type': 'success',
                'sticky': False,
            }
        }