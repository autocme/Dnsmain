# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
#
# Copyright (C) 2023 JAAH

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from validator_collection import validators, errors
import re

class Subdomain(models.Model):
    _name = 'dns.subdomain'
    _description = 'DNS Subdomain'
    _order = 'name'

    name = fields.Char(string='Subdomain', required=True)
    domain_id = fields.Many2one('dns.domain', string='Domain', required=True, ondelete='cascade')
    conversion_method = fields.Selection([
        ('a', 'A Record'),
        ('cname', 'CNAME Record')
    ], string='Conversion Method', required=True, default='a')
    value = fields.Char(string='Value', required=True)
    full_domain = fields.Char(string='Full Domain', compute='_compute_full_domain', store=True)
    active = fields.Boolean(default=True)
    
    _sql_constraints = [
        ('name_domain_unique', 'UNIQUE(name, domain_id)', 'Subdomain must be unique per domain!')
    ]
    
    @api.depends('name', 'domain_id.name')
    def _compute_full_domain(self):
        for record in self:
            if record.name and record.domain_id and record.domain_id.name:
                record.full_domain = f"{record.name}.{record.domain_id.name}"
            else:
                record.full_domain = False
    
    @api.constrains('name')
    def _check_subdomain_name(self):
        for record in self:
            # Check if subdomain name follows valid hostname rules
            if not record.name:
                continue
            
            # Validate subdomain format - alphanumeric, hyphens, no spaces
            if not re.match(r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?$', record.name):
                raise ValidationError(_("Invalid subdomain name: %s. Subdomains can only contain letters, numbers, and hyphens (not at the beginning or end).") % record.name)
    
    @api.constrains('full_domain')
    def _check_full_domain(self):
        for record in self:
            if not record.full_domain:
                continue
                
            try:
                # Validate full domain using validator-collection
                validators.domain(record.full_domain)
            except errors.InvalidDomainError:
                raise ValidationError(_("Invalid full domain: %s") % record.full_domain)

    @api.constrains('value', 'conversion_method')
    def _check_record_value(self):
        for record in self:
            if record.conversion_method == 'a':
                try:
                    # Validate IP address for A records
                    validators.ip_address(record.value)
                except errors.InvalidIPAddressError:
                    raise ValidationError(_("Invalid IP address for A record: %s") % record.value)
            elif record.conversion_method == 'cname':
                try:
                    # Validate domain for CNAME records
                    validators.domain(record.value)
                except errors.InvalidDomainError:
                    raise ValidationError(_("Invalid domain for CNAME record: %s") % record.value)
