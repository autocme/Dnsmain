# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
#
# Copyright (C) 2023 JAAH

import logging
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from botocore.exceptions import ClientError

_logger = logging.getLogger(__name__)

class Subdomain(models.Model):
    _inherit = 'dns.subdomain'
    
    route53_record_id = fields.Char(string='Route 53 Record ID', readonly=True)
    route53_sync = fields.Boolean(string='Sync with Route 53', related='domain_id.route53_sync', store=True, readonly=True)
    route53_sync_status = fields.Selection([
        ('not_synced', 'Not Synced'),
        ('synced', 'Synced'),
        ('error', 'Error')
    ], string='Route 53 Sync Status', compute='_compute_route53_sync_status', store=True)
    route53_last_sync = fields.Datetime(string='Last Route 53 Sync')
    route53_error_message = fields.Text(string='Route 53 Error Message')
    
    @api.depends('domain_id.route53_sync', 'route53_last_sync', 'route53_error_message')
    def _compute_route53_sync_status(self):
        for subdomain in self:
            domain = subdomain.domain_id
            if not domain.route53_sync or not domain.route53_config_id:
                subdomain.route53_sync_status = 'not_synced'
            elif subdomain.route53_error_message:
                subdomain.route53_sync_status = 'error'
            elif subdomain.route53_last_sync:
                subdomain.route53_sync_status = 'synced'
            else:
                subdomain.route53_sync_status = 'not_synced'
    
    def sync_to_route53(self):
        """Sync this subdomain to Route 53"""
        self.ensure_one()
        domain = self.domain_id
        
        if not domain.route53_sync:
            _logger.info("Route 53 sync disabled for domain %s", domain.name)
            return False
            
        if not domain.route53_config_id:
            error = "No Route 53 configuration set for domain %s" % domain.name
            _logger.error(error)
            self.write({'route53_error_message': error})
            return False
            
        if not domain.route53_hosted_zone_id:
            error = "No hosted zone ID specified or found for domain %s" % domain.name
            _logger.error(error)
            self.write({'route53_error_message': error})
            return False
        
        try:
            config = domain.route53_config_id
            client = config._get_route53_client()
            
            # Map type to Route 53 record type
            record_type_mapping = {
                'a': 'A',
                'aaaa': 'AAAA',
                'caa': 'CAA',
                'cname': 'CNAME',
                'ds': 'DS',
                'https': 'HTTPS',
                'mx': 'MX',
                'naptr': 'NAPTR',
                'ns': 'NS',
                'ptr': 'PTR',
                'soa': 'SOA',
                'spf': 'SPF',
                'srv': 'SRV',
                'sshfp': 'SSHFP',
                'svcb': 'SVCB',
                'tlsa': 'TLSA',
                'txt': 'TXT'
            }
            
            record_type = record_type_mapping.get(self.type, 'TXT')
            record_value = self.value
            
            # Process value based on record type
            if record_type in ['CNAME', 'NS', 'PTR', 'MX', 'SRV']:
                # Domain records require trailing dot
                if not record_value.endswith('.'):
                    if record_type == 'MX':
                        # For MX records, only add dot to domain part
                        parts = record_value.split(' ', 1)
                        if len(parts) == 2:
                            record_value = f"{parts[0]} {parts[1]}."
                        else:
                            record_value = record_value + '.'
                    elif record_type == 'SRV':
                        # For SRV records, only add dot to target part
                        parts = record_value.rsplit(' ', 1)
                        if len(parts) == 2:
                            record_value = f"{parts[0]} {parts[1]}."
                        else:
                            record_value = record_value + '.'
                    else:
                        record_value = record_value + '.'
            
            elif record_type == 'TXT' or record_type == 'SPF':
                # TXT records need to be enclosed in quotes if not already
                if not (record_value.startswith('"') and record_value.endswith('"')):
                    record_value = f'"{record_value}"'
                
            # Create or update Route 53 record
            response = client.change_resource_record_sets(
                HostedZoneId=domain.route53_hosted_zone_id,
                ChangeBatch={
                    'Comment': 'Updated by Odoo DNS Management',
                    'Changes': [
                        {
                            'Action': 'UPSERT',
                            'ResourceRecordSet': {
                                'Name': self.full_domain + '.',  # Add trailing dot
                                'Type': record_type,
                                'TTL': self.ttl,
                                'ResourceRecords': [
                                    {
                                        'Value': record_value
                                    }
                                ]
                            }
                        }
                    ]
                }
            )
            
            # Update subdomain record with sync info
            self.write({
                'route53_record_id': response.get('ChangeInfo', {}).get('Id'),
                'route53_last_sync': fields.Datetime.now(),
                'route53_error_message': False,
            })
            
            _logger.info("Successfully synced subdomain %s to Route 53", self.full_domain)
            return True
            
        except ClientError as e:
            error_message = str(e)
            _logger.error("Route 53 sync error for %s: %s", self.full_domain, error_message)
            
            self.write({
                'route53_error_message': error_message,
            })
            
            return False
    
    @api.model_create_multi
    def create(self, vals_list):
        records = super(Subdomain, self).create(vals_list)
        # Sync new records to Route 53 if enabled
        for record in records:
            if record.domain_id.route53_sync:
                record.sync_to_route53()
        return records
    
    def write(self, vals):
        result = super(Subdomain, self).write(vals)
        # Sync updated records to Route 53 if enabled and relevant fields changed
        if any(field in vals for field in ['name', 'domain_id', 'type', 'value', 'ttl']):
            for record in self:
                if record.domain_id.route53_sync:
                    record.sync_to_route53()
        return result
    
    def unlink(self):
        # Delete records from Route 53 before deleting from Odoo
        for record in self:
            if record.domain_id.route53_sync and record.domain_id.route53_config_id and record.domain_id.route53_hosted_zone_id:
                try:
                    config = record.domain_id.route53_config_id
                    client = config._get_route53_client()
                    
                    # Delete Route 53 record using the same type mapping as sync_to_route53
                    record_type_mapping = {
                        'a': 'A',
                        'aaaa': 'AAAA',
                        'caa': 'CAA',
                        'cname': 'CNAME',
                        'ds': 'DS',
                        'https': 'HTTPS',
                        'mx': 'MX',
                        'naptr': 'NAPTR',
                        'ns': 'NS',
                        'ptr': 'PTR',
                        'soa': 'SOA',
                        'spf': 'SPF',
                        'srv': 'SRV',
                        'sshfp': 'SSHFP',
                        'svcb': 'SVCB',
                        'tlsa': 'TLSA',
                        'txt': 'TXT'
                    }
                    
                    record_type = record_type_mapping.get(record.type, 'TXT')
                    record_value = record.value
                    
                    # Process value based on record type
                    if record_type in ['CNAME', 'NS', 'PTR', 'MX', 'SRV']:
                        # Domain records require trailing dot
                        if not record_value.endswith('.'):
                            if record_type == 'MX':
                                # For MX records, only add dot to domain part
                                parts = record_value.split(' ', 1)
                                if len(parts) == 2:
                                    record_value = f"{parts[0]} {parts[1]}."
                                else:
                                    record_value = record_value + '.'
                            elif record_type == 'SRV':
                                # For SRV records, only add dot to target part
                                parts = record_value.rsplit(' ', 1)
                                if len(parts) == 2:
                                    record_value = f"{parts[0]} {parts[1]}."
                                else:
                                    record_value = record_value + '.'
                            else:
                                record_value = record_value + '.'
                    
                    elif record_type == 'TXT' or record_type == 'SPF':
                        # TXT records need to be enclosed in quotes if not already
                        if not (record_value.startswith('"') and record_value.endswith('"')):
                            record_value = f'"{record_value}"'
                    
                    client.change_resource_record_sets(
                        HostedZoneId=record.domain_id.route53_hosted_zone_id,
                        ChangeBatch={
                            'Comment': 'Deleted by Odoo DNS Management',
                            'Changes': [
                                {
                                    'Action': 'DELETE',
                                    'ResourceRecordSet': {
                                        'Name': record.full_domain + '.',  # Add trailing dot
                                        'Type': record_type,
                                        'TTL': record.ttl,
                                        'ResourceRecords': [
                                            {
                                                'Value': record_value
                                            }
                                        ]
                                    }
                                }
                            ]
                        }
                    )
                    
                    _logger.info("Successfully deleted subdomain %s from Route 53", record.full_domain)
                except Exception as e:
                    _logger.error("Failed to delete subdomain %s from Route 53: %s", record.full_domain, str(e))
                    # Continue with deletion even if Route 53 deletion fails
        
        return super(Subdomain, self).unlink()
        
    @api.model
    def sync_route53_records(self, domain_id=None):
        """
        Sync AWS Route 53 records to Odoo DNS records
        This creates DNS record entries in Odoo for any records found in Route 53
        that don't already exist.
        
        Args:
            domain_id: Optional domain ID to limit the sync to a specific domain
        """
        # Get domains to sync
        Domain = self.env['dns.domain']
        if domain_id:
            domains = Domain.browse(domain_id)
            if not domains.exists():
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Domain Not Found'),
                        'message': _('The specified domain was not found.'),
                        'sticky': False,
                        'type': 'warning',
                    }
                }
        else:
            domains = Domain.search([
                ('route53_sync', '=', True),
                ('route53_config_id', '!=', False),
                ('route53_hosted_zone_id', '!=', False)
            ])
        
        if not domains:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No Domains Found'),
                    'message': _('No domains with Route 53 sync enabled were found.'),
                    'sticky': False,
                    'type': 'warning',
                }
            }
        
        record_count = 0
        error_messages = []
        
        # Process each domain
        for domain in domains:
            try:
                # Skip if essential data is missing
                if not domain.route53_sync or not domain.route53_config_id or not domain.route53_hosted_zone_id:
                    continue
                
                # Get the Route 53 client
                config = domain.route53_config_id
                client = config._get_route53_client()
                hosted_zone_id = domain.route53_hosted_zone_id
                
                # List records in the hosted zone
                response = client.list_resource_record_sets(
                    HostedZoneId=hosted_zone_id
                )
                
                # Process each record
                for record in response.get('ResourceRecordSets', []):
                    record_type = record.get('Type')
                    
                    # Check if this is a supported record type
                    supported_types = ['A', 'AAAA', 'CAA', 'CNAME', 'DS', 'HTTPS', 'MX', 
                                      'NAPTR', 'NS', 'PTR', 'SOA', 'SPF', 'SRV', 'SSHFP', 
                                      'SVCB', 'TLSA', 'TXT']
                    if record_type not in supported_types:
                        # Skip unsupported record types
                        _logger.info("Skipping unsupported record type: %s for %s", record_type, record.get('Name', ''))
                        continue
                    
                    # Get the full domain name and strip trailing dot
                    full_name = record.get('Name', '').rstrip('.')
                    domain_name = domain.name
                    
                    # Skip the domain's own records (SOA, NS, etc.)
                    if full_name == domain_name:
                        continue
                    
                    # Extract subdomain part
                    if full_name.endswith(domain_name):
                        subdomain_part = full_name[:-len(domain_name)-1]  # -1 for the dot
                    else:
                        continue  # Not part of this domain
                    
                    # Get record value
                    record_value = ''
                    if record.get('ResourceRecords'):
                        # Get the raw value
                        raw_value = record['ResourceRecords'][0]['Value']
                        
                        # Process the value based on record type
                        if record_type == 'A':
                            # For A records (IPv4 addresses)
                            record_value = raw_value
                        
                        elif record_type == 'AAAA':
                            # For AAAA records (IPv6 addresses)
                            record_value = raw_value
                        
                        elif record_type in ['CNAME', 'NS', 'PTR']:
                            # Domain names, remove trailing dot
                            record_value = raw_value.rstrip('.')
                        
                        elif record_type == 'MX':
                            # MX records have priority and domain
                            # Format: "10 mail.example.com."
                            parts = raw_value.split(' ', 1)
                            if len(parts) == 2:
                                domain_part = parts[1].rstrip('.')
                                record_value = f"{parts[0]} {domain_part}"
                            else:
                                record_value = raw_value
                        
                        elif record_type == 'TXT' or record_type == 'SPF':
                            # Handle TXT and SPF records, remove quotes
                            record_value = raw_value.strip('"')
                        
                        elif record_type == 'SRV':
                            # SRV records: priority weight port target
                            # Format: "1 10 5269 xmpp-server.example.com."
                            parts = raw_value.rsplit(' ', 1)
                            if len(parts) == 2:
                                record_value = f"{parts[0]} {parts[1].rstrip('.')}"
                            else:
                                record_value = raw_value
                        
                        elif record_type == 'CAA':
                            # CAA records
                            # Format: "0 issue \"ca.example.com\""
                            record_value = raw_value
                        
                        else:
                            # For all other record types
                            record_value = raw_value
                    
                    elif record.get('AliasTarget'):
                        # Handle alias records
                        alias_target = record.get('AliasTarget', {}).get('DNSName', '').rstrip('.')
                        record_value = f"ALIAS: {alias_target}"
                    
                    else:
                        continue  # Skip if no valid value
                    
                    # Additional validation for empty values
                    if not record_value:
                        _logger.warning("Empty value for %s record: %s - skipping", record_type, record.get('Name', ''))
                        continue
                    
                    # Check if DNS record already exists
                    existing_record = self.search([
                        ('name', '=', subdomain_part),
                        ('domain_id', '=', domain.id)
                    ], limit=1)
                    
                    if not existing_record:
                        # Create new DNS record
                        # Map AWS record type to our conversion method
                        type_mapping = {
                            'A': 'a',
                            'AAAA': 'aaaa',
                            'CAA': 'caa',
                            'CNAME': 'cname',
                            'DS': 'ds',
                            'HTTPS': 'https',
                            'MX': 'mx',
                            'NAPTR': 'naptr',
                            'NS': 'ns',
                            'PTR': 'ptr',
                            'SOA': 'soa',
                            'SPF': 'spf',
                            'SRV': 'srv',
                            'SSHFP': 'sshfp',
                            'SVCB': 'svcb',
                            'TLSA': 'tlsa',
                            'TXT': 'txt'
                        }
                        record_type_value = type_mapping.get(record_type, 'txt')  # Default to TXT for unknown types
                        # Get TTL from Route53 or use default
                        ttl = record.get('TTL', 300)
                        
                        new_record = self.create({
                            'name': subdomain_part,
                            'domain_id': domain.id,
                            'type': record_type_value,
                            'value': record_value,
                            'ttl': ttl,
                            'route53_record_id': f"{record_type}:{full_name}",
                            'route53_last_sync': fields.Datetime.now(),
                        })
                        record_count += 1
                    else:
                        # Only update if it doesn't have a Route 53 record ID
                        if not existing_record.route53_record_id:
                            # Use the same mapping as for new records
                            type_mapping = {
                                'A': 'a',
                                'AAAA': 'aaaa',
                                'CAA': 'caa',
                                'CNAME': 'cname',
                                'DS': 'ds',
                                'HTTPS': 'https',
                                'MX': 'mx',
                                'NAPTR': 'naptr',
                                'NS': 'ns',
                                'PTR': 'ptr',
                                'SOA': 'soa',
                                'SPF': 'spf',
                                'SRV': 'srv',
                                'SSHFP': 'sshfp',
                                'SVCB': 'svcb',
                                'TLSA': 'tlsa',
                                'TXT': 'txt'
                            }
                            record_type_value = type_mapping.get(record_type, 'txt')
                            # Get TTL from Route53 or use default
                            ttl = record.get('TTL', 300)
                            
                            existing_record.write({
                                'type': record_type_value,
                                'value': record_value,
                                'ttl': ttl,
                                'route53_record_id': f"{record_type}:{full_name}",
                                'route53_last_sync': fields.Datetime.now(),
                            })
                            record_count += 1
                
                # Update domain last sync time
                domain.write({
                    'route53_last_sync': fields.Datetime.now(),
                    'route53_error_message': False,
                })
                
            except Exception as e:
                error_message = f"Error syncing domain '{domain.name}': {str(e)}"
                _logger.error(error_message)
                error_messages.append(error_message)
                domain.write({
                    'route53_error_message': error_message,
                })
        
        # Generate response message
        if error_messages:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sync Completed With Errors'),
                    'message': _(f"Created/updated {record_count} DNS records. Errors: {'; '.join(error_messages)}"),
                    'sticky': True,
                    'type': 'warning',
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sync Completed'),
                    'message': _(f"Successfully created/updated {record_count} DNS records from Route 53."),
                    'sticky': False,
                    'type': 'success',
                }
            }