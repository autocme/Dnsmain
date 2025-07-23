#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'
    
    # SaaS-related custom fields for tracking SaaS package purchases
    x_saas_package_id = fields.Integer(
        string='SaaS Package ID',
        help='ID of the SaaS package associated with this payment transaction'
    )
    
    x_saas_billing_cycle = fields.Char(
        string='SaaS Billing Cycle',
        help='Billing cycle for the SaaS package (monthly/yearly)'
    )
    
    x_saas_user_id = fields.Integer(
        string='SaaS User ID', 
        help='ID of the user who purchased the SaaS package'
    )
    
    def write(self, vals):
        """Override write to handle SaaS client creation on payment completion"""
        result = super(PaymentTransaction, self).write(vals)
        
        # Check if transaction state changed to 'done' (successful payment)
        if 'state' in vals and vals['state'] == 'done':
            for tx in self:
                if tx.x_saas_package_id:
                    _logger.info(f'SaaS payment transaction {tx.id} completed successfully')
                    tx._handle_saas_payment_success()
        
        return result
    
    def _handle_saas_payment_success(self):
        """Create SaaS client after successful payment"""
        self.ensure_one()
        
        try:
            _logger.info(f'Processing SaaS payment success for transaction {self.id}')
            
            # Check if we have all required SaaS context
            if not all([self.x_saas_package_id, self.x_saas_billing_cycle, self.x_saas_user_id]):
                _logger.warning(f'Transaction {self.id} missing SaaS context fields')
                return
            
            # Get the SaaS package
            package = self.env['saas.package'].sudo().browse(self.x_saas_package_id)
            if not package.exists():
                _logger.error(f'SaaS package {self.x_saas_package_id} not found for transaction {self.id}')
                return
            
            # Get the user
            user = self.env['res.users'].sudo().browse(self.x_saas_user_id)
            if not user.exists():
                _logger.error(f'User {self.x_saas_user_id} not found for transaction {self.id}')
                return
            
            # Check if SaaS client already exists
            existing_client = self.env['saas.client'].sudo().search([
                ('sc_partner_id', '=', user.partner_id.id),
                ('sc_package_id', '=', package.id),
                ('sc_subscription_period', '=', self.x_saas_billing_cycle)
            ], limit=1)
            
            if existing_client:
                _logger.info(f'SaaS client {existing_client.id} already exists for transaction {self.id}')
                return
            
            # Create SaaS client
            client_data = {
                'sc_partner_id': user.partner_id.id,
                'sc_package_id': package.id,
                'sc_subscription_period': self.x_saas_billing_cycle,
                'sc_is_free_trial': False,  # This is a paid transaction
                'sc_status': 'draft'
            }
            
            client = self.env['saas.client'].sudo().create(client_data)
            _logger.info(f'Created SaaS client {client.id} for paid transaction {self.id}')
            
            # Create subscription and invoice
            if hasattr(client, '_create_subscription'):
                client._create_subscription()
                _logger.info(f'Created subscription for SaaS client {client.id}')
            
        except Exception as e:
            _logger.error(f'Error handling SaaS payment success for transaction {self.id}: {str(e)}')
            import traceback
            _logger.error(traceback.format_exc())