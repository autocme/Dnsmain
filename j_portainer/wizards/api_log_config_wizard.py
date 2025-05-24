#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)

class APILogConfigWizard(models.TransientModel):
    _name = 'j_portainer.api_log.config.wizard'
    _description = 'API Log Configuration Wizard'
    
    days = fields.Integer(
        string='Retention Period (Days)',
        default=1,
        required=True,
        help="Number of days to keep API logs. Logs older than this will be automatically deleted by the scheduled action."
    )
    
    @api.model
    def default_get(self, fields_list):
        """Get default values for the wizard"""
        res = super(APILogConfigWizard, self).default_get(fields_list)
        
        # Get current value from system parameters
        param_days = self.env['ir.config_parameter'].sudo().get_param('j_portainer.api_log_purge_days', '1')
        try:
            days = int(param_days)
            if days < 1:
                days = 1
        except (ValueError, TypeError):
            days = 1
            
        res['days'] = days
        return res
    
    @api.constrains('days')
    def _check_days(self):
        """Ensure days is a positive integer"""
        for record in self:
            if record.days < 1:
                raise ValidationError(_("Retention period must be at least 1 day"))
    
    def save_config(self):
        """Save configuration to system parameters"""
        self.ensure_one()
        
        # Update system parameter
        self.env['ir.config_parameter'].sudo().set_param('j_portainer.api_log_purge_days', str(self.days))
        
        # Show success message
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Configuration Saved'),
                'message': _('API log retention period set to %d days') % self.days,
                'sticky': False,
                'type': 'success',
            }
        }
    
    def run_purge_now(self):
        """Run the purge operation immediately with the specified days"""
        self.ensure_one()
        
        # Update system parameter first
        self.env['ir.config_parameter'].sudo().set_param('j_portainer.api_log_purge_days', str(self.days))
        
        # Run the purge operation
        count = self.env['j_portainer.api_log'].purge_old_logs(days=self.days)
        
        # Show success message
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Logs Purged'),
                'message': _('Purged %d API logs older than %d days') % (count, self.days),
                'sticky': False,
                'type': 'success',
            }
        }