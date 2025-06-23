#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _

class DnsSubdomainInherit(models.Model):
    _inherit = 'dns.subdomain'
    
    saas_client_id = fields.Many2one(
        comodel_name='saas.client',
        string='SaaS Client',
        help='The SaaS client that owns this subdomain'
    )