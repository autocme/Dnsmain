# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
#
# Copyright (C) 2023 JAAH

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from validator_collection import validators, errors

class Domain(models.Model):
    _name = 'dns.domain'
    _description = 'DNS Domain'
    _order = 'name'

    name = fields.Char(string='Domain Name', required=True, index=True)
    description = fields.Text(string='Description')
    region = fields.Char(string='Region', help='Geographic region where the domain is primarily used')
    active = fields.Boolean(default=True)
    subdomain_ids = fields.One2many('dns.subdomain', 'domain_id', string='Subdomains')
    subdomain_count = fields.Integer(compute='_compute_subdomain_count', string='Subdomain Count')
    
    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'Domain name must be unique!')
    ]
    
    @api.depends('subdomain_ids')
    def _compute_subdomain_count(self):
        for domain in self:
            domain.subdomain_count = len(domain.subdomain_ids)
    
    @api.constrains('name')
    def _check_domain_name(self):
        for record in self:
            try:
                # Validate domain name using validator-collection
                validators.domain(record.name)
            except errors.InvalidDomainError:
                raise ValidationError(_("Invalid domain name: %s") % record.name)
    
    def action_view_subdomains(self):
        self.ensure_one()
        return {
            'name': _('Subdomains'),
            'view_mode': 'tree,form',
            'res_model': 'dns.subdomain',
            'domain': [('domain_id', '=', self.id)],
            'type': 'ir.actions.act_window',
            'context': {'default_domain_id': self.id},
        }
