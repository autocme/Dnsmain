#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _

class DnsSubdomainInherit(models.Model):
    _inherit = 'dns.subdomain'
    
    client_id = fields.Many2one(
        comodel_name='saas.client',
        string='SaaS Client',
        required=False,
        tracking=True,
        help='The SaaS client associated with this DNS subdomain.'
    )