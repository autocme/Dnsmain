#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _

class DnsSubdomainInherit(models.Model):
    _inherit = 'dns.subdomain'
    
    # Additional fields or methods for DNS subdomain can be added here if needed in the future