#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    """
    Extend Account Move to trigger SaaS client deployment when invoices are paid
    """
    _inherit = 'account.move'
    
    @api.model
    def _trigger_saas_client_deployment(self):
        """
        Check and deploy SaaS clients when their subscription invoices are paid
        """
        # Find all paid invoices related to SaaS subscriptions
        paid_invoices = self.search([
            ('payment_state', '=', 'paid'),
            ('move_type', '=', 'out_invoice'),
            ('subscription_id', '!=', False)
        ])
        
        deployed_clients = []
        for invoice in paid_invoices:
            # Find SaaS clients linked to this subscription
            saas_clients = self.env['saas.client'].search([
                ('sc_subscription_id', '=', invoice.subscription_id.id),
                ('sc_status', '=', 'draft')
            ])
            
            for client in saas_clients:
                if client.check_and_deploy_if_invoice_paid():
                    deployed_clients.append(client.id)
        
        return deployed_clients
    
    def write(self, vals):
        """
        Override write to trigger deployment when payment_state changes to paid
        """
        result = super().write(vals)
        
        # Check if payment_state was updated to 'paid'
        if vals.get('payment_state') == 'paid':
            for record in self:
                if record.move_type == 'out_invoice' and record.subscription_id:
                    # Find SaaS client for this subscription
                    saas_client = self.env['saas.client'].search([
                        ('sc_subscription_id', '=', record.subscription_id.id),
                        ('sc_status', '=', 'draft')
                    ], limit=1)
                    
                    if saas_client:
                        saas_client.check_and_deploy_if_invoice_paid()
        
        return result