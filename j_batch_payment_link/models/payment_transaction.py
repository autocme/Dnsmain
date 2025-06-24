#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class PaymentTransaction(models.Model):
    """
    Extend Payment Transaction to add batch payment relationship.
    """
    _inherit = 'payment.transaction'

    # ========================================================================
    # FIELDS
    # ========================================================================
    
    batch_payment_id = fields.Many2one(
        comodel_name='batch.payment',
        string='Batch Payment',
        readonly=True,
        help='Batch payment associated with this transaction'
    )