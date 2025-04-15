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
        ('aaaa', 'AAAA Record'),
        ('caa', 'CAA Record'),
        ('cname', 'CNAME Record'),
        ('ds', 'DS Record'),
        ('https', 'HTTPS Record'),
        ('mx', 'MX Record'),
        ('naptr', 'NAPTR Record'),
        ('ns', 'NS Record'),
        ('ptr', 'PTR Record'),
        ('soa', 'SOA Record'),
        ('spf', 'SPF Record'),
        ('srv', 'SRV Record'),
        ('sshfp', 'SSHFP Record'),
        ('svcb', 'SVCB Record'),
        ('tlsa', 'TLSA Record'),
        ('txt', 'TXT Record')
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
            
            # Check for special DNS record types (like DKIM or SPF) which can contain underscores
            is_special_record = '_' in record.name
            
            if is_special_record:
                # Special DNS records - allow underscores but validate general format
                if not re.match(r'^[a-zA-Z0-9_]([a-zA-Z0-9_\-\.]{0,61}[a-zA-Z0-9_])?$', record.name):
                    raise ValidationError(_("Invalid special DNS record name: %s. Special records can contain letters, numbers, hyphens, and underscores.") % record.name)
            else:
                # Standard subdomain rules - alphanumeric, hyphens, no spaces
                if not re.match(r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?$', record.name):
                    raise ValidationError(_("Invalid subdomain name: %s. Subdomains can only contain letters, numbers, and hyphens (not at the beginning or end).") % record.name)
    
    @api.constrains('full_domain')
    def _check_full_domain(self):
        for record in self:
            if not record.full_domain:
                continue
            
            # Skip strict validation for special records (containing underscores)
            if '_' in record.full_domain:
                # Basic validation for special DNS records
                if not re.match(r'^[a-zA-Z0-9_][a-zA-Z0-9_\-\.]{0,253}[a-zA-Z0-9_]$', record.full_domain):
                    raise ValidationError(_("Invalid special record full domain: %s") % record.full_domain)
            else:
                try:
                    # Validate standard domains using validator-collection
                    validators.domain(record.full_domain)
                except errors.InvalidDomainError:
                    raise ValidationError(_("Invalid full domain: %s") % record.full_domain)

    @api.constrains('value', 'conversion_method')
    def _check_record_value(self):
        for record in self:
            # IP address validation for A and AAAA records
            if record.conversion_method == 'a':
                try:
                    # Validate IPv4 address for A records
                    validators.ip_address(record.value)
                    # Further check that it's IPv4, not IPv6
                    if ':' in record.value:
                        raise ValidationError(_("A records must use IPv4 addresses, not IPv6: %s") % record.value)
                except errors.InvalidIPAddressError:
                    raise ValidationError(_("Invalid IP address for A record: %s") % record.value)
            
            elif record.conversion_method == 'aaaa':
                try:
                    # Validate IPv6 address for AAAA records
                    validators.ip_address(record.value)
                    # Check that it's actually IPv6
                    if ':' not in record.value:
                        raise ValidationError(_("AAAA records must use IPv6 addresses, not IPv4: %s") % record.value)
                except errors.InvalidIPAddressError:
                    raise ValidationError(_("Invalid IPv6 address for AAAA record: %s") % record.value)
            
            # Domain name validation for records pointing to other domains
            elif record.conversion_method in ['cname', 'mx', 'ns', 'ptr']:
                try:
                    # Validate domain
                    validators.domain(record.value.rstrip('.'))
                except errors.InvalidDomainError:
                    raise ValidationError(_("Invalid domain for %s record: %s") % (record.conversion_method.upper(), record.value))
            
            # MX records need priority
            elif record.conversion_method == 'mx':
                # Check for priority value (e.g., "10 mail.example.com")
                if not re.match(r'^\d+\s+[a-zA-Z0-9][a-zA-Z0-9\-\.]+[a-zA-Z0-9]\.?$', record.value):
                    raise ValidationError(_("Invalid MX record format. Should be 'priority domain' (e.g., '10 mail.example.com'): %s") % record.value)
            
            # Basic validation for TXT and SPF records
            elif record.conversion_method in ['txt', 'spf']:
                if not record.value or len(record.value) > 255:
                    raise ValidationError(_("TXT/SPF record value must be between 1 and 255 characters: %s") % record.value)
            
            # SRV records validation
            elif record.conversion_method == 'srv':
                if not re.match(r'^\d+\s+\d+\s+\d+\s+[a-zA-Z0-9][a-zA-Z0-9\-\.]+[a-zA-Z0-9]\.?$', record.value):
                    raise ValidationError(_("Invalid SRV record format. Should be 'priority weight port target' (e.g., '0 5 5060 sip.example.com'): %s") % record.value)
            
            # CAA records validation
            elif record.conversion_method == 'caa':
                if not re.match(r'^\d+\s+(issue|issuewild|iodef)\s+"[^"]+"$', record.value):
                    raise ValidationError(_("Invalid CAA record format. Should be 'flag tag \"value\"' (e.g., '0 issue \"ca.example.com\"'): %s") % record.value)
            
            # Basic length validation for other record types
            else:
                if not record.value:
                    raise ValidationError(_("Record value cannot be empty"))
                elif len(record.value) > 500:  # General limit for most DNS values
                    raise ValidationError(_("Record value exceeds maximum length: %s") % record.value)
