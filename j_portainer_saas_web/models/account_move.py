#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'
    
    is_saas_first_invoice = fields.Boolean(
        string='SaaS First Invoice',
        default=False,
        help='Indicates if this is the first invoice generated for a SaaS subscription'
    )
    
    @api.model
    def write(self, vals):
        """Override write to detect payment status changes for SaaS invoices"""
        result = super(AccountMove, self).write(vals)
        
        # Check if payment_state is being updated to 'paid'
        if 'payment_state' in vals and vals['payment_state'] == 'paid':
            self._handle_saas_payment_completion()
        
        return result
    
    def _handle_saas_payment_completion(self):
        """Handle SaaS client deployment when first invoice is paid"""
        for invoice in self:
            # Only process invoices marked as SaaS first invoices
            if not invoice.is_saas_first_invoice:
                continue
            
            try:
                # Find the SaaS client related to this invoice
                saas_client = self.env['saas.client'].sudo().search([
                    ('sc_partner_id', '=', invoice.partner_id.id),
                    ('sc_status', 'in', ['draft', 'ready'])
                ], limit=1)
                
                if not saas_client:
                    _logger.warning(f"No SaaS client found for paid invoice {invoice.name}")
                    continue
                
                _logger.info(f"SaaS first invoice {invoice.name} paid for client {saas_client.id}, initiating deployment...")
                
                # Deploy the client
                if saas_client.sc_status in ['draft', 'ready']:
                    saas_client.action_deploy_client()
                    _logger.info(f"Successfully deployed SaaS client {saas_client.id} after payment of invoice {invoice.name}")
                
            except Exception as e:
                _logger.error(f"Error handling SaaS payment completion for invoice {invoice.name}: {str(e)}")
                continue