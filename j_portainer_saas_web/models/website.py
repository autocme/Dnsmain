#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields


class Website(models.Model):
    _inherit = 'website'
    
    subscription_agreement_url = fields.Char(
        string='Subscription Agreement URL',
        default='/terms',
        help='URL for the subscription agreement page (editable through website editor)'
    )
    
    privacy_policy_url = fields.Char(
        string='Privacy Policy URL', 
        default='/privacy',
        help='URL for the privacy policy page (editable through website editor)'
    )
    
    legal_agreement_text = fields.Html(
        string='Legal Agreement Text',
        help='Legal agreement text displayed on purchase confirmation page (editable through website editor)'
    )