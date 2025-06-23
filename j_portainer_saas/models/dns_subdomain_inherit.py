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
    
    def action_view_saas_client(self):
        """Open the related SaaS client form."""
        self.ensure_one()
        if not self.saas_client_id:
            return False
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'SaaS Client',
            'res_model': 'saas.client',
            'res_id': self.saas_client_id.id,
            'view_mode': 'form',
            'target': 'current',
            'context': dict(self.env.context),
        }