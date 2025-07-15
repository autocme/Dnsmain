#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    """
    Extension of payment.transaction model to support SaaS-specific fields
    Only loads if payment module is available
    """
    _inherit = 'payment.transaction'
    
    def __init__(self, pool, cr):
        # Only initialize if payment module is available
        if 'payment.transaction' in pool:
            super().__init__(pool, cr)
        else:
            _logger.warning("Payment module not available, skipping payment.transaction extension")
    
    # SaaS-specific fields for tracking package and billing information
    x_saas_package_id = fields.Integer(
        string='SaaS Package ID',
        help='ID of the SaaS package being purchased'
    )
    
    x_saas_billing_cycle = fields.Char(
        string='SaaS Billing Cycle',
        help='Billing cycle for the SaaS package (monthly/yearly)'
    )
    
    x_saas_user_id = fields.Integer(
        string='SaaS User ID',
        help='ID of the user purchasing the SaaS package'
    )
    
    x_saas_client_id = fields.Integer(
        string='SaaS Client ID',
        help='ID of the created SaaS client after successful payment'
    )
    
    @api.model
    def _get_processing_values(self):
        """
        Override to include SaaS-specific processing values
        """
        values = super()._get_processing_values()
        
        # Add SaaS-specific processing information
        if self.x_saas_package_id:
            try:
                package = self.env['saas.package'].sudo().browse(self.x_saas_package_id)
                if package.exists():
                    values.update({
                        'saas_package_name': package.pkg_name,
                        'saas_billing_cycle': self.x_saas_billing_cycle,
                        'saas_package_description': package.pkg_description,
                    })
            except Exception as e:
                _logger.warning(f"Failed to get SaaS package info for transaction {self.id}: {str(e)}")
        
        return values
    
    def _post_process_after_done(self):
        """
        Override to handle SaaS client creation after successful payment
        """
        super()._post_process_after_done()
        
        # Create SaaS client if this is a SaaS transaction
        if self.x_saas_package_id and not self.x_saas_client_id:
            try:
                self._create_saas_client_from_transaction()
            except Exception as e:
                _logger.error(f"Failed to create SaaS client from transaction {self.id}: {str(e)}")
    
    def _create_saas_client_from_transaction(self):
        """
        Create SaaS client from successful payment transaction
        """
        if not self.x_saas_package_id:
            return
        
        try:
            package = self.env['saas.package'].sudo().browse(self.x_saas_package_id)
            user = self.env['res.users'].sudo().browse(self.x_saas_user_id)
            
            if not package.exists() or not user.exists():
                _logger.error(f"Package {self.x_saas_package_id} or user {self.x_saas_user_id} not found")
                return
            
            # Create SaaS client
            client_vals = {
                'sc_partner_id': user.partner_id.id,
                'sc_package_id': package.id,
                'sc_subscription_period': self.x_saas_billing_cycle,
                'sc_is_free_trial': False,
                'sc_status': 'draft',
            }
            
            client = self.env['saas.client'].sudo().create(client_vals)
            
            # Update transaction with client ID
            self.x_saas_client_id = client.id
            
            _logger.info(f"SaaS client {client.id} created from payment transaction {self.id}")
            
            # Link payment to subscription invoice
            self._link_payment_to_subscription(client)
            
            # Auto-deploy client after successful payment
            try:
                client.action_deploy()
                _logger.info(f"SaaS client {client.id} deployed automatically")
            except Exception as e:
                _logger.warning(f"Auto-deployment failed for client {client.id}: {str(e)}")
            
            return client
            
        except Exception as e:
            _logger.error(f"Failed to create SaaS client from transaction {self.id}: {str(e)}")
            raise
    
    def _link_payment_to_subscription(self, client):
        """
        Link payment transaction to subscription invoice
        """
        try:
            subscription = client.sc_subscription_id
            if not subscription:
                return
            
            # Get subscription invoices
            invoices = subscription.recurring_invoice_line_ids.mapped('invoice_id')
            if not invoices:
                return
            
            invoice = invoices[0]
            
            # Create payment record
            payment_vals = {
                'payment_type': 'inbound',
                'partner_type': 'customer',
                'partner_id': self.partner_id.id,
                'amount': self.amount,
                'currency_id': self.currency_id.id,
                'payment_transaction_id': self.id,
                'ref': f'Payment for {client.sc_package_id.pkg_name} - {self.reference}',
            }
            
            # Get journal from provider (Odoo 17) or acquirer (older versions)
            journal = None
            if hasattr(self, 'provider_id') and self.provider_id:
                journal = self.provider_id.journal_id
            elif hasattr(self, 'acquirer_id') and self.acquirer_id:
                journal = self.acquirer_id.journal_id
            
            if journal:
                payment_vals['journal_id'] = journal.id
                # Get payment method
                payment_methods = journal.inbound_payment_method_ids
                if payment_methods:
                    payment_vals['payment_method_id'] = payment_methods[0].id
            
            payment = self.env['account.payment'].sudo().create(payment_vals)
            payment.post()
            
            # Reconcile with invoice
            receivable_line = payment.move_line_ids.filtered(lambda r: r.account_id.internal_type == 'receivable')
            if receivable_line:
                invoice.js_assign_outstanding_line(receivable_line.id)
            
            _logger.info(f"Payment linked to invoice {invoice.id} for transaction {self.reference}")
            
        except Exception as e:
            _logger.error(f"Failed to link payment to subscription for transaction {self.id}: {str(e)}")