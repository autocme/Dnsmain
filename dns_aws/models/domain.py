# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
#
# Copyright (C) 2023 JAAH

import logging
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

class Domain(models.Model):
    _inherit = 'dns.domain'
    
    route53_config_id = fields.Many2one('dns.route53.config', string='Route 53 Configuration')
    route53_hosted_zone_id = fields.Char(string='Route 53 Hosted Zone ID', help='If empty, we will try to find it automatically')
    route53_sync = fields.Boolean(string='Sync with Route 53', default=False)
    route53_sync_status = fields.Selection([
        ('not_synced', 'Not Synced'),
        ('synced', 'Synced'),
        ('error', 'Error')
    ], string='Route 53 Sync Status', compute='_compute_route53_sync_status', store=True)
    route53_last_sync = fields.Datetime(string='Last Route 53 Sync')
    route53_error_message = fields.Text(string='Route 53 Error Message')
    
    @api.depends('route53_sync', 'route53_config_id', 'route53_last_sync', 'route53_error_message')
    def _compute_route53_sync_status(self):
        for domain in self:
            if not domain.route53_sync or not domain.route53_config_id:
                domain.route53_sync_status = 'not_synced'
            elif domain.route53_error_message:
                domain.route53_sync_status = 'error'
            elif domain.route53_last_sync:
                domain.route53_sync_status = 'synced'
            else:
                domain.route53_sync_status = 'not_synced'
    
    @api.onchange('route53_config_id', 'name')
    def _onchange_route53_config(self):
        if self.route53_config_id and self.name and not self.route53_hosted_zone_id:
            try:
                config = self.route53_config_id
                hosted_zone_id = config.get_hosted_zone_id_by_domain(self.name)
                if hosted_zone_id:
                    self.route53_hosted_zone_id = hosted_zone_id
            except Exception as e:
                _logger.error("Error getting hosted zone ID: %s", str(e))
                # Don't raise error in onchange, just log it
    
    def sync_all_subdomains_to_route53(self):
        """Sync all subdomains for this domain to Route 53"""
        self.ensure_one()
        
        if not self.route53_sync:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sync Disabled'),
                    'message': _('Route 53 sync is disabled for this domain.'),
                    'sticky': False,
                    'type': 'warning',
                }
            }
            
        if not self.route53_config_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Config Missing'),
                    'message': _('Please select a Route 53 configuration for this domain.'),
                    'sticky': False,
                    'type': 'warning',
                }
            }
            
        if not self.route53_hosted_zone_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Hosted Zone Missing'),
                    'message': _('No hosted zone ID specified or found for this domain.'),
                    'sticky': False,
                    'type': 'warning',
                }
            }
        
        try:
            # Trigger sync for all subdomains
            for subdomain in self.subdomain_ids:
                subdomain.sync_to_route53()
                
            self.write({
                'route53_last_sync': fields.Datetime.now(),
                'route53_error_message': False,
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sync Complete'),
                    'message': _('All subdomains have been synchronized with Route 53.'),
                    'sticky': False,
                    'type': 'success',
                }
            }
        except Exception as e:
            error_message = str(e)
            _logger.error("Route 53 sync error: %s", error_message)
            
            self.write({
                'route53_error_message': error_message,
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sync Error'),
                    'message': error_message,
                    'sticky': False,
                    'type': 'danger',
                }
            }