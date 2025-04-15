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
    _description = 'DNS Records'
    _order = 'name'

    name = fields.Char(string='DNS Record Name', required=True)
    domain_id = fields.Many2one('dns.domain', string='Domain', required=True, ondelete='cascade')
    type = fields.Selection([
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
    ], string='Type', required=True, default='a')
    value = fields.Char(string='Value', required=True)
    ttl = fields.Integer(string='TTL', required=True, default=300, 
                         help='Time To Live in seconds. Default is 300 seconds (5 minutes)')
    full_domain = fields.Char(string='Full Domain', compute='_compute_full_domain', store=True)
    active = fields.Boolean(default=True)
    placeholder_helper = fields.Char(compute='_compute_placeholder_helper')
    
    _sql_constraints = [
        ('name_domain_unique', 'UNIQUE(name, domain_id)', 'DNS Record must be unique per domain!')
    ]
    
    @api.depends('name', 'domain_id.name')
    def _compute_full_domain(self):
        for record in self:
            if record.name and record.domain_id and record.domain_id.name:
                record.full_domain = f"{record.name}.{record.domain_id.name}"
            else:
                record.full_domain = False
                
    @api.depends('type')
    def _compute_placeholder_helper(self):
        """
        Provides a placeholder text based on the selected record type.
        This replaces the deprecated attrs="{'placeholder': [...]}" in Odoo 17.
        """
        for record in self:
            placeholder = "Record value"
            if record.type == 'a':
                placeholder = "IPv4 address (e.g., 192.168.1.1)"
            elif record.type == 'aaaa':
                placeholder = "IPv6 address (e.g., 2001:db8::1)"
            elif record.type == 'cname':
                placeholder = "Domain name (e.g., target.example.com)"
            elif record.type == 'mx':
                placeholder = "Priority and domain (e.g., 10 mail.example.com)"
            elif record.type == 'ns':
                placeholder = "Domain name (e.g., ns1.example.com)"
            elif record.type == 'txt':
                placeholder = "Text value (e.g., v=spf1 include:_spf.example.com ~all)"
            elif record.type == 'srv':
                placeholder = "Priority weight port target (e.g., 0 5 5060 sip.example.com)"
            elif record.type == 'caa':
                placeholder = "Flag tag value (e.g., 0 issue \"ca.example.com\")"
            elif record.type == 'ds':
                placeholder = "Key tag algorithm digest type digest (e.g., 12345 8 2 ABCDEF...)"
            elif record.type == 'https':
                placeholder = "Priority target params (e.g., 1 . alpn=h3,h2 ipv4hint=192.0.2.1)"
            elif record.type == 'svcb':
                placeholder = "Priority target params (e.g., 1 . alpn=h3,h2 ipv4hint=192.0.2.1)"
            elif record.type == 'tlsa':
                placeholder = "Certificate usage selector matching type data (e.g., 3 0 1 ABCDEF...)"
            elif record.type == 'sshfp':
                placeholder = "Algorithm fingerprint-type fingerprint (e.g., 2 1 123456789ABCDEF...)"
            elif record.type == 'naptr':
                placeholder = "Order pref. flags service regexp replacement (e.g., 10 100 \"S\" \"SIP+D2U\" \"!^.*$!sip:example.com!\" _sip._udp.example.com)"
            elif record.type == 'ptr':
                placeholder = "Domain name (e.g., host.example.com)"
            elif record.type == 'spf':
                placeholder = "SPF record (e.g., v=spf1 ip4:192.168.1.1 ~all)"
            elif record.type == 'soa':
                placeholder = "Primary server email TTLs (e.g., ns1.example.com. admin.example.com. 2023010101 3600 900 1209600 86400)"
            
            record.placeholder_helper = placeholder
    
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
                # Check for wildcard subdomain (e.g., *.example.com)
                if record.name == '*':
                    # Wildcard is allowed as a standalone subdomain name
                    pass
                # Standard subdomain rules - alphanumeric, hyphens, no spaces
                elif not re.match(r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?$', record.name):
                    raise ValidationError(_("Invalid subdomain name: %s. Subdomains can only contain letters, numbers, and hyphens (not at the beginning or end).") % record.name)
    
    @api.constrains('full_domain')
    def _check_full_domain(self):
        for record in self:
            if not record.full_domain:
                continue
            
            # Skip strict validation for special records (containing underscores) or wildcards
            if '_' in record.full_domain:
                # Basic validation for special DNS records
                if not re.match(r'^[a-zA-Z0-9_][a-zA-Z0-9_\-\.]{0,253}[a-zA-Z0-9_]$', record.full_domain):
                    raise ValidationError(_("Invalid special record full domain: %s") % record.full_domain)
            elif record.full_domain.startswith('*.'):
                # Process wildcard domains
                # Check if the domain after the *. is valid
                base_domain = record.full_domain[2:]  # Remove the *. prefix
                try:
                    validators.domain(base_domain)
                except errors.InvalidDomainError:
                    raise ValidationError(_("Invalid wildcard domain: %s") % record.full_domain)
            else:
                try:
                    # Validate standard domains using validator-collection
                    validators.domain(record.full_domain)
                except errors.InvalidDomainError:
                    raise ValidationError(_("Invalid full domain: %s") % record.full_domain)

    @api.constrains('ttl')
    def _check_ttl_value(self):
        for record in self:
            if record.ttl < 0:
                raise ValidationError(_("TTL value cannot be negative"))
            elif record.ttl > 86400 * 7:  # 7 days in seconds
                raise ValidationError(_("TTL value too high. Maximum allowed is 7 days (604800 seconds)"))
    
    @api.constrains('value', 'type')
    def _check_record_value(self):
        for record in self:
            # IP address validation for A and AAAA records
            if record.type == 'a':
                try:
                    # Validate IPv4 address for A records
                    validators.ip_address(record.value)
                    # Further check that it's IPv4, not IPv6
                    if ':' in record.value:
                        raise ValidationError(_("A records must use IPv4 addresses, not IPv6: %s") % record.value)
                except errors.InvalidIPAddressError:
                    raise ValidationError(_("Invalid IP address for A record: %s") % record.value)
            
            elif record.type == 'aaaa':
                try:
                    # Validate IPv6 address for AAAA records
                    validators.ip_address(record.value)
                    # Check that it's actually IPv6
                    if ':' not in record.value:
                        raise ValidationError(_("AAAA records must use IPv6 addresses, not IPv4: %s") % record.value)
                except errors.InvalidIPAddressError:
                    raise ValidationError(_("Invalid IPv6 address for AAAA record: %s") % record.value)
            
            # Domain name validation for records pointing to other domains
            elif record.type in ['cname', 'mx', 'ns', 'ptr']:
                try:
                    # Validate domain
                    validators.domain(record.value.rstrip('.'))
                except errors.InvalidDomainError:
                    raise ValidationError(_("Invalid domain for %s record: %s") % (record.type.upper(), record.value))
            
            # MX records need priority
            elif record.type == 'mx':
                # Check for priority value (e.g., "10 mail.example.com")
                if not re.match(r'^\d+\s+[a-zA-Z0-9][a-zA-Z0-9\-\.]+[a-zA-Z0-9]\.?$', record.value):
                    raise ValidationError(_("Invalid MX record format. Should be 'priority domain' (e.g., '10 mail.example.com'): %s") % record.value)
            
            # Basic validation for TXT and SPF records
            elif record.type in ['txt', 'spf']:
                if not record.value or len(record.value) > 255:
                    raise ValidationError(_("TXT/SPF record value must be between 1 and 255 characters: %s") % record.value)
            
            # SRV records validation
            elif record.type == 'srv':
                if not re.match(r'^\d+\s+\d+\s+\d+\s+[a-zA-Z0-9][a-zA-Z0-9\-\.]+[a-zA-Z0-9]\.?$', record.value):
                    raise ValidationError(_("Invalid SRV record format. Should be 'priority weight port target' (e.g., '0 5 5060 sip.example.com'): %s") % record.value)
            
            # CAA records validation
            elif record.type == 'caa':
                if not re.match(r'^\d+\s+(issue|issuewild|iodef)\s+"[^"]+"$', record.value):
                    raise ValidationError(_("Invalid CAA record format. Should be 'flag tag \"value\"' (e.g., '0 issue \"ca.example.com\"'): %s") % record.value)
            
            # DS (Delegation Signer) records validation
            elif record.type == 'ds':
                if not re.match(r'^\d+\s+\d+\s+\d+\s+[A-Fa-f0-9]+$', record.value):
                    raise ValidationError(_("Invalid DS record format. Should be 'key_tag algorithm_number digest_type digest' (e.g., '12345 8 2 ABCDEF...): %s") % record.value)
            
            # HTTPS and SVCB records validation
            elif record.type in ['https', 'svcb']:
                if not re.match(r'^\d+\s+\S+\s+.+$', record.value):
                    raise ValidationError(_("Invalid HTTPS/SVCB record format. Should be 'priority target-name param-list' (e.g., '1 . alpn=h3,h2 ipv4hint=192.0.2.1'): %s") % record.value)
            
            # SSHFP (SSH Fingerprint) record validation
            elif record.type == 'sshfp':
                if not re.match(r'^[1-4]\s+[1-2]\s+[A-Fa-f0-9]+$', record.value):
                    raise ValidationError(_("Invalid SSHFP record format. Should be 'algorithm fingerprint-type fingerprint' (e.g., '2 1 123456789ABCDEF...): %s") % record.value)
            
            # TLSA record validation
            elif record.type == 'tlsa':
                if not re.match(r'^[0-3]\s+[0-1]\s+[0-2]\s+[A-Fa-f0-9]+$', record.value):
                    raise ValidationError(_("Invalid TLSA record format. Should be 'cert-usage selector matching-type certdata' (e.g., '3 0 1 ABCDEF...): %s") % record.value)
            
            # NAPTR record validation
            elif record.type == 'naptr':
                if not re.match(r'^\d+\s+\d+\s+"[^"]+"\s+"[^"]*"\s+"[^"]*"\s+\S+$', record.value):
                    raise ValidationError(_("Invalid NAPTR record format. Should be 'order preference \"flags\" \"service\" \"regexp\" replacement' (e.g., '10 100 \"S\" \"SIP+D2U\" \"!^.*$!sip:cs.example.com!\" _sip._udp.example.com.'): %s") % record.value)
            
            # Basic length validation for other record types
            else:
                if not record.value:
                    raise ValidationError(_("Record value cannot be empty"))
                elif len(record.value) > 500:  # General limit for most DNS values
                    raise ValidationError(_("Record value exceeds maximum length: %s") % record.value)
