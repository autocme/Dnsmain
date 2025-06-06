# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
#
# Copyright (C) 2023 JAAH

import logging
import boto3
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from botocore.exceptions import ClientError

_logger = logging.getLogger(__name__)

class Subdomain(models.Model):
    _inherit = ['dns.subdomain', 'dns.aws.client.mixin']
    _name = 'dns.subdomain'
    
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
                
            # Get existing record first if we have a route53_record_id
            existing_record = None
            if self.route53_record_id:
                try:
                    # Try to find the existing record to ensure we're truly updating
                    record_name = self.full_domain + '.'  # Add trailing dot
                    _logger.info("Looking for existing record: %s (%s)", record_name, record_type)
                    
                    # Get current records that match our name and type using the AWS client mixin
                    response = self.execute_aws_operation(
                        service_name='route53',
                        operation_name='list_resource_record_sets',
                        HostedZoneId=domain.route53_hosted_zone_id,
                        StartRecordName=record_name,
                        StartRecordType=record_type,
                        MaxItems='10'
                    )
                    
                    for aws_record in response.get('ResourceRecordSets', []):
                        if aws_record.get('Name') == record_name and aws_record.get('Type') == record_type:
                            existing_record = aws_record
                            _logger.info("Found existing record: %s", aws_record)
                            break
                except Exception as e:
                    _logger.warning("Error fetching existing record: %s", str(e))
            
            # If we found an existing record and need to update it, first delete, then create
            if existing_record and self.route53_record_id:
                _logger.info("Updating existing Route 53 record: %s", self.full_domain)
                
                # Build the change batch with both DELETE and CREATE operations
                change_batch = {
                    'Comment': 'Updated by Odoo DNS Management',
                    'Changes': [
                        {
                            'Action': 'DELETE',
                            'ResourceRecordSet': existing_record
                        },
                        {
                            'Action': 'CREATE',
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
            else:
                # If no existing record found, use UPSERT
                _logger.info("Creating new Route 53 record: %s", self.full_domain)
                change_batch = {
                    'Comment': 'Created by Odoo DNS Management',
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
            
            # Execute the change using the AWS client mixin
            response = self.execute_aws_operation(
                service_name='route53',
                operation_name='change_resource_record_sets',
                HostedZoneId=domain.route53_hosted_zone_id,
                ChangeBatch=change_batch
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
        # Store old values to handle name changes
        old_values = {}
        if 'name' in vals:
            for record in self:
                old_values[record.id] = {
                    'name': record.name,
                    'full_domain': record.full_domain,
                    'domain_id': record.domain_id.id,
                    'type': record.type,
                    'ttl': record.ttl,
                    'value': record.value
                }
        
        result = super(Subdomain, self).write(vals)
        
        # Handle special case: if name was changed, first delete the old record
        if 'name' in vals and old_values:
            for record in self:
                if record.id in old_values and record.domain_id.route53_sync:
                    try:
                        old_data = old_values[record.id]
                        # Only if the domain hasn't changed
                        if old_data['domain_id'] == record.domain_id.id:
                            config = record.domain_id.route53_config_id
                            if config:
                                client = config._get_route53_client()
                                
                                # Map old type to Route 53 record type
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
                                
                                old_record_type = record_type_mapping.get(old_data['type'], 'TXT')
                                old_record_value = old_data['value']
                                
                                # Process value based on record type (same as in sync_to_route53)
                                if old_record_type in ['CNAME', 'NS', 'PTR', 'MX', 'SRV']:
                                    if not old_record_value.endswith('.'):
                                        if old_record_type == 'MX':
                                            parts = old_record_value.split(' ', 1)
                                            if len(parts) == 2:
                                                old_record_value = f"{parts[0]} {parts[1]}."
                                            else:
                                                old_record_value = old_record_value + '.'
                                        elif old_record_type == 'SRV':
                                            parts = old_record_value.rsplit(' ', 1)
                                            if len(parts) == 2:
                                                old_record_value = f"{parts[0]} {parts[1]}."
                                            else:
                                                old_record_value = old_record_value + '.'
                                        else:
                                            old_record_value = old_record_value + '.'
                                
                                elif old_record_type == 'TXT' or old_record_type == 'SPF':
                                    if not (old_record_value.startswith('"') and old_record_value.endswith('"')):
                                        old_record_value = f'"{old_record_value}"'
                                
                                # Delete old record first
                                _logger.info("Deleting old record %s before updating name", old_data['full_domain'])
                                try:
                                    client.change_resource_record_sets(
                                        HostedZoneId=record.domain_id.route53_hosted_zone_id,
                                        ChangeBatch={
                                            'Comment': 'Deleted by Odoo DNS Management due to name change',
                                            'Changes': [
                                                {
                                                    'Action': 'DELETE',
                                                    'ResourceRecordSet': {
                                                        'Name': old_data['full_domain'] + '.',  # Add trailing dot
                                                        'Type': old_record_type,
                                                        'TTL': old_data['ttl'],
                                                        'ResourceRecords': [
                                                            {
                                                                'Value': old_record_value
                                                            }
                                                        ]
                                                    }
                                                }
                                            ]
                                        }
                                    )
                                    _logger.info("Successfully deleted old record %s", old_data['full_domain'])
                                except Exception as e:
                                    _logger.warning("Error deleting old record %s: %s", old_data['full_domain'], str(e))
                    except Exception as e:
                        _logger.error("Error in pre-delete for renamed record: %s", str(e))
                        # Continue with sync even if this fails
        
        # Sync updated records to Route 53 if enabled and relevant fields changed
        if any(field in vals for field in ['name', 'domain_id', 'type', 'value', 'ttl']):
            for record in self:
                if record.domain_id.route53_sync:
                    record.sync_to_route53()
        
        return result
    
    def unlink(self):
        # Delete records from Route 53 before deleting from Odoo
        # Skip Route 53 deletion if context flag is set
        if self.env.context.get('skip_route53_delete'):
            return super(Subdomain, self).unlink()
            
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
    def sync_route53_records(self, domain_id=None, delete_orphans=True):
        """
        Sync AWS Route 53 records to Odoo DNS records
        This creates DNS record entries in Odoo for any records found in Route 53
        that don't already exist, and removes records from Odoo that no longer exist in Route 53.
        
        Args:
            domain_id: Optional domain ID to limit the sync to a specific domain
            delete_orphans: Whether to delete Odoo records that no longer exist in AWS
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
        deleted_count = 0
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
                
                # Log number of records found in Route 53
                aws_record_count = len(response.get('ResourceRecordSets', []))
                _logger.info("Found %d records in Route 53 for domain %s", aws_record_count, domain.name)
                
                # Process each record
                for record in response.get('ResourceRecordSets', []):
                    record_type = record.get('Type')
                    record_name = record.get('Name', '')
                    
                    # Enhanced logging for better debugging
                    _logger.info("Processing AWS record: Type=%s, Name=%s", record_type, record_name)
                    
                    # Check if this is a supported record type
                    supported_types = ['A', 'AAAA', 'CAA', 'CNAME', 'DS', 'HTTPS', 'MX', 
                                      'NAPTR', 'NS', 'PTR', 'SOA', 'SPF', 'SRV', 'SSHFP', 
                                      'SVCB', 'TLSA', 'TXT']
                    if record_type not in supported_types:
                        # Skip unsupported record types
                        _logger.info("Skipping unsupported record type: %s for %s", record_type, record_name)
                        continue
                    
                    # Get the full domain name and strip trailing dot
                    full_name = record_name.rstrip('.')
                    domain_name = domain.name
                    
                    # Skip the domain's own records (SOA, NS, etc.)
                    if full_name == domain_name:
                        _logger.info("Skipping apex record for domain: %s", full_name)
                        continue
                    
                    # Extract subdomain part with more robust logic
                    subdomain_part = ''
                    
                    # Check if the record belongs to this domain
                    if full_name == domain_name:
                        # This is the apex record (@), but we already skipped it above
                        _logger.info("Skipping domain apex record again (should not happen)")
                        continue
                    elif full_name.endswith('.' + domain_name):
                        # Regular subdomain: remove domain name and trailing dot
                        subdomain_part = full_name[:-len(domain_name)-1]  # -1 for the dot
                        _logger.info("Extracted subdomain part: '%s' from '%s'", subdomain_part, full_name)
                    elif not domain_name.startswith(full_name):
                        # If full_name doesn't end with domain_name and domain_name doesn't start with full_name
                        # then this record likely belongs to a different domain
                        _logger.info("Record %s doesn't seem to belong to domain %s - skipping", full_name, domain_name)
                        continue
                    
                    # Handle wildcard domains: Route 53 encodes '*' as '\052' in responses
                    if '\\052' in subdomain_part:
                        old_part = subdomain_part
                        subdomain_part = subdomain_part.replace('\\052', '*')
                        _logger.info("Converted wildcard: '%s' to '%s'", old_part, subdomain_part)
                    elif r'\052' in subdomain_part:
                        old_part = subdomain_part
                        subdomain_part = subdomain_part.replace(r'\052', '*')
                        _logger.info("Converted raw wildcard: '%s' to '%s'", old_part, subdomain_part)
                    
                    # Additional logging
                    _logger.info("Final subdomain name: '%s' for record: Type=%s, Name=%s", 
                                subdomain_part, record_type, record_name)
                    
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
                    
                    # Map AWS record type to our type field
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
                    record_id = f"{record_type}:{full_name}"
                    
                    # First check if we have a record with the same Route 53 ID
                    existing_record = self.search([
                        ('domain_id', '=', domain.id),
                        ('route53_record_id', '=', record_id)
                    ], limit=1)
                    
                    if not existing_record:
                        # If no record with same ID, try to find by name and domain
                        existing_record = self.search([
                            ('name', '=', subdomain_part),
                            ('domain_id', '=', domain.id),
                            ('type', '=', record_type_value)
                        ], limit=1)
                    
                    if not existing_record:
                        # Log creation
                        _logger.info("Creating new record: %s.%s (%s)", subdomain_part, domain_name, record_type)
                        
                        # Create new DNS record
                        new_record = self.create({
                            'name': subdomain_part,
                            'domain_id': domain.id,
                            'type': record_type_value,
                            'value': record_value,
                            'ttl': ttl,
                            'route53_record_id': record_id,
                            'route53_last_sync': fields.Datetime.now(),
                        })
                        record_count += 1
                    else:
                        # Update existing record
                        # Check if any field needs updating
                        update_needed = False
                        
                        if existing_record.route53_record_id != record_id:
                            update_needed = True
                            _logger.info("Updating record ID: %s -> %s", existing_record.route53_record_id, record_id)
                        
                        if existing_record.type != record_type_value:
                            update_needed = True
                            _logger.info("Updating record type: %s -> %s", existing_record.type, record_type_value)
                        
                        if existing_record.value != record_value:
                            update_needed = True
                            _logger.info("Updating record value: %s -> %s", existing_record.value, record_value)
                        
                        if existing_record.ttl != ttl:
                            update_needed = True
                            _logger.info("Updating record TTL: %s -> %s", existing_record.ttl, ttl)
                        
                        if update_needed:
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
                
                # Track Route 53 records that exist for this domain
                # First collect all AWS records BEFORE processing them
                # This ensures we don't miss any records during deletion detection
                aws_records = []
                _logger.info("Beginning to collect existing AWS records for domain %s", domain.name)
                
                # Collect all record identifiers that exist in AWS for this domain
                # Process each record in the original response to ensure consistency
                for aws_record in response.get('ResourceRecordSets', []):
                    aws_record_type = aws_record.get('Type')
                    aws_record_name = aws_record.get('Name', '')
                    
                    # Skip unsupported record types and domain apex records
                    if aws_record_type not in supported_types:
                        continue
                        
                    aws_full_name = aws_record_name.rstrip('.')
                    if aws_full_name == domain_name:
                        continue
                        
                    # Check if record belongs to this domain
                    if aws_full_name.endswith('.' + domain_name) or aws_full_name == domain_name:
                        # This is a record of our domain
                        record_id = f"{aws_record_type}:{aws_full_name}"
                        aws_records.append(record_id)
                        _logger.info("Found AWS record: %s", record_id)
                
                _logger.info("Collected %d total AWS records for domain %s", len(aws_records), domain.name)
                
                # Find records in Odoo that no longer exist in AWS and delete them
                domain_records = self.search([
                    ('domain_id', '=', domain.id),
                    ('route53_record_id', '!=', False)  # Remove route53_sync condition as it's handled at domain level
                ])
                
                # Find and log records that no longer exist in AWS
                _logger.info("Checking for Odoo records that no longer exist in AWS Route 53")
                _logger.info("Found %d Odoo records with Route 53 IDs for domain %s", len(domain_records), domain.name)
                
                to_delete = self.env['dns.subdomain']
                orphaned_records = []  # Track orphaned records even if we don't delete them
                
                for odoo_record in domain_records:
                    if not odoo_record.route53_record_id:
                        _logger.info("Record %s has no Route 53 ID - skipping", odoo_record.full_domain)
                        continue
                        
                    # Log the record we're checking
                    _logger.info("Checking if record still exists in AWS: %s (ID: %s)", 
                               odoo_record.full_domain, odoo_record.route53_record_id)
                               
                    if odoo_record.route53_record_id not in aws_records:
                        _logger.info("Record %s with ID %s no longer exists in Route 53, marking as orphaned", 
                                    odoo_record.full_domain, odoo_record.route53_record_id)
                        orphaned_records.append(odoo_record.full_domain)
                        
                        if delete_orphans:
                            to_delete |= odoo_record
                    else:
                        _logger.info("Record %s still exists in AWS, keeping", odoo_record.full_domain)
                
                # Report orphaned records even if we're not deleting them
                if orphaned_records:
                    if delete_orphans:
                        # Only delete if delete_orphans is True
                        _logger.info("Records to delete: %s", ", ".join([r.full_domain for r in to_delete]))
                        _logger.info("Deleting %d DNS records that no longer exist in Route 53", len(to_delete))
                        deleted_count += len(to_delete)
                        
                        # Set special context flag to avoid triggering Route 53 deletion when deleting from Odoo
                        to_delete.with_context(skip_route53_delete=True).unlink()
                    else:
                        _logger.info("Found %d orphaned records but not deleting due to delete_orphans=False", 
                                    len(orphaned_records))
                        _logger.info("Orphaned records: %s", ", ".join(orphaned_records))
                else:
                    _logger.info("No orphaned records found for domain %s", domain.name)
                
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
            message = _(f"Successfully synced with Route 53. Created/updated {record_count} records")
            if deleted_count > 0:
                message += _(f", deleted {deleted_count} records that no longer exist in AWS")
            message += "."
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sync Completed'),
                    'message': message,
                    'sticky': False,
                    'type': 'success',
                }
            }