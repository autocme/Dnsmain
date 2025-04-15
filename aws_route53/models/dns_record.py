# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
#
# Copyright (C) 2023 JAAH

import logging
import re
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

class Route53DNSRecord(models.Model):
    """
    Represents a DNS record in an AWS Route 53 hosted zone.
    """
    _name = 'aws.route53.dns.record'
    _description = 'Route 53 DNS Record'
    _inherit = ['aws.service.implementation.mixin', 'aws.service.logger']
    _rec_name = 'record_name'
    _order = 'hosted_zone_id, name, type'
    
    hosted_zone_id = fields.Many2one('aws.route53.hosted.zone', string='Hosted Zone', 
                                     required=True, ondelete='cascade')
    domain_name = fields.Char(related='hosted_zone_id.domain_name', string='Domain', readonly=True)
    
    name = fields.Char(string='Record Name', required=True, 
                      help='Use @ for the root domain or subdomain name without the domain part')
    type = fields.Selection([
        ('A', 'A - IPv4 Address'),
        ('AAAA', 'AAAA - IPv6 Address'),
        ('CAA', 'CAA - Certificate Authority Authorization'),
        ('CNAME', 'CNAME - Canonical Name'),
        ('DS', 'DS - Delegation Signer'),
        ('MX', 'MX - Mail Exchange'),
        ('NAPTR', 'NAPTR - Name Authority Pointer'),
        ('NS', 'NS - Name Server'),
        ('PTR', 'PTR - Pointer'),
        ('SOA', 'SOA - Start of Authority'),
        ('SPF', 'SPF - Sender Policy Framework'),
        ('SRV', 'SRV - Service Locator'),
        ('TXT', 'TXT - Text'),
        ('TLSA', 'TLSA - TLSA Record'),
        ('SSHFP', 'SSHFP - SSH Public Key Fingerprint'),
        ('HTTPS', 'HTTPS - HTTPS Record'),
        ('SVCB', 'SVCB - Service Binding'),
    ], string='Record Type', required=True, default='A')
    
    ttl = fields.Integer(string='TTL', required=True, default=300,
                        help='Time To Live in seconds. Default is 300 seconds (5 minutes)')
    value = fields.Text(string='Value', required=True,
                       help='For multiple values, separate with semicolons (;)')
    
    record_name = fields.Char(string='Full Record Name', compute='_compute_record_name', store=True)
    aws_record_id = fields.Char(string='AWS Record ID', readonly=True)
    
    active = fields.Boolean(default=True)
    sync_status = fields.Selection([
        ('not_synced', 'Not Synced'),
        ('syncing', 'Syncing'),
        ('synced', 'Synced'),
        ('error', 'Error')
    ], string='Sync Status', default='not_synced')
    last_sync = fields.Datetime(string='Last Sync')
    sync_message = fields.Text(string='Sync Message')
    
    _sql_constraints = [
        ('name_type_zone_unique', 'UNIQUE(hosted_zone_id, name, type)', 
         'Record name and type must be unique per hosted zone!')
    ]
    
    @api.depends('name', 'domain_name', 'type')
    def _compute_record_name(self):
        """Compute the full DNS record name"""
        for record in self:
            if record.name == '@':
                record.record_name = f"@ ({record.domain_name}) [{record.type}]"
            else:
                record.record_name = f"{record.name}.{record.domain_name} [{record.type}]"
    
    @api.model
    def create(self, vals):
        """
        Create a new DNS record both in Odoo and AWS Route 53.
        """
        # Create locally first
        record = super(Route53DNSRecord, self).create(vals)
        
        # Don't create in AWS if sync is disabled or for data import
        if self.env.context.get('import_file') or self.env.context.get('no_aws_sync'):
            return record
        
        # Create in AWS
        try:
            record._create_record_in_aws()
        except Exception as e:
            record.write({
                'sync_status': 'error',
                'sync_message': str(e)
            })
            _logger.error("Failed to create Route 53 DNS record: %s", str(e))
            
        return record
    
    def write(self, vals):
        """
        Update DNS record both in Odoo and AWS Route 53.
        """
        result = super(Route53DNSRecord, self).write(vals)
        
        # Don't update in AWS if sync is disabled or for data import
        if self.env.context.get('import_file') or self.env.context.get('no_aws_sync'):
            return result
        
        # Check if relevant fields were changed
        relevant_fields = ['name', 'type', 'ttl', 'value', 'active']
        if any(field in vals for field in relevant_fields):
            for record in self:
                try:
                    record._update_record_in_aws()
                except Exception as e:
                    record.write({
                        'sync_status': 'error',
                        'sync_message': str(e)
                    })
                    _logger.error("Failed to update Route 53 DNS record: %s", str(e))
        
        return result
    
    def unlink(self):
        """
        Delete DNS record from AWS Route 53 before deleting from Odoo.
        """
        if not self.env.context.get('no_aws_sync'):
            for record in self:
                try:
                    record._delete_record_from_aws()
                except Exception as e:
                    raise UserError(_("Cannot delete DNS record from AWS: %s") % str(e))
        
        return super(Route53DNSRecord, self).unlink()
    
    def _create_record_in_aws(self):
        """
        Create the DNS record in AWS Route 53.
        """
        self.ensure_one()
        
        # Get the hosted zone
        hosted_zone = self.hosted_zone_id
        if not hosted_zone.hosted_zone_id:
            raise UserError(_("Hosted zone does not have an AWS ID. Cannot create record."))
        
        # Get Route 53 client
        route53 = self.get_service_client('route53')
        
        # Prepare record name
        if self.name == '@':
            record_name = hosted_zone.domain_name
        else:
            record_name = f"{self.name}.{hosted_zone.domain_name}"
            
        # Add trailing dot if needed
        if not record_name.endswith('.'):
            record_name += '.'
            
        # Prepare resource records
        values = self.value.split(';')
        resource_records = [{'Value': value.strip()} for value in values if value.strip()]
        
        # Prepare change batch
        change_batch = {
            'Changes': [
                {
                    'Action': 'CREATE',
                    'ResourceRecordSet': {
                        'Name': record_name,
                        'Type': self.type,
                        'TTL': self.ttl,
                        'ResourceRecords': resource_records
                    }
                }
            ]
        }
        
        # Create the record
        success, result = self.aws_operation_with_logging(
            service_name='route53',
            operation='change_resource_record_sets',
            with_result=True,
            HostedZoneId=hosted_zone.hosted_zone_id,
            ChangeBatch=change_batch
        )
        
        if not success:
            raise UserError(_("Failed to create DNS record: %s") % result)
            
        # Update local record with sync status
        self.write({
            'aws_record_id': f"{record_name}:{self.type}",
            'sync_status': 'synced',
            'last_sync': fields.Datetime.now(),
            'sync_message': _("Record created successfully")
        })
    
    def _update_record_in_aws(self):
        """
        Update the DNS record in AWS Route 53.
        """
        self.ensure_one()
        
        # Get the hosted zone
        hosted_zone = self.hosted_zone_id
        if not hosted_zone.hosted_zone_id:
            raise UserError(_("Hosted zone does not have an AWS ID. Cannot update record."))
        
        # Get Route 53 client
        route53 = self.get_service_client('route53')
        
        # Prepare old record name for deletion (if changed)
        old_record_name = None
        if self.aws_record_id:
            old_record_parts = self.aws_record_id.split(':')
            if len(old_record_parts) >= 2:
                old_record_name = old_record_parts[0]
                old_record_type = old_record_parts[1]
        
        # Prepare new record name
        if self.name == '@':
            record_name = hosted_zone.domain_name
        else:
            record_name = f"{self.name}.{hosted_zone.domain_name}"
            
        # Add trailing dot if needed
        if not record_name.endswith('.'):
            record_name += '.'
            
        # Prepare resource records
        values = self.value.split(';')
        resource_records = [{'Value': value.strip()} for value in values if value.strip()]
        
        # Prepare change batch
        changes = []
        
        # Delete old record if name changed
        if old_record_name and (old_record_name != record_name or old_record_type != self.type):
            changes.append({
                'Action': 'DELETE',
                'ResourceRecordSet': {
                    'Name': old_record_name,
                    'Type': old_record_type,
                    # Note: For DELETE, we need the exact original values, which we don't have
                    # This may not work in all cases
                    'TTL': self.ttl,
                    'ResourceRecords': resource_records
                }
            })
            
        # Create/update new record
        changes.append({
            'Action': 'UPSERT',  # UPSERT will create if not exists or update if exists
            'ResourceRecordSet': {
                'Name': record_name,
                'Type': self.type,
                'TTL': self.ttl,
                'ResourceRecords': resource_records
            }
        })
        
        change_batch = {'Changes': changes}
        
        # Update the record
        success, result = self.aws_operation_with_logging(
            service_name='route53',
            operation='change_resource_record_sets',
            with_result=True,
            HostedZoneId=hosted_zone.hosted_zone_id,
            ChangeBatch=change_batch
        )
        
        if not success:
            raise UserError(_("Failed to update DNS record: %s") % result)
            
        # Update local record with sync status
        self.write({
            'aws_record_id': f"{record_name}:{self.type}",
            'sync_status': 'synced',
            'last_sync': fields.Datetime.now(),
            'sync_message': _("Record updated successfully")
        })
    
    def _delete_record_from_aws(self):
        """
        Delete the DNS record from AWS Route 53.
        """
        self.ensure_one()
        
        # Get the hosted zone
        hosted_zone = self.hosted_zone_id
        if not hosted_zone.hosted_zone_id:
            return
            
        if not self.aws_record_id:
            return
            
        # Get Route 53 client
        route53 = self.get_service_client('route53')
        
        # Extract record information
        record_parts = self.aws_record_id.split(':')
        if len(record_parts) < 2:
            return
            
        record_name = record_parts[0]
        record_type = record_parts[1]
        
        # Prepare resource records
        values = self.value.split(';')
        resource_records = [{'Value': value.strip()} for value in values if value.strip()]
        
        # Prepare change batch
        change_batch = {
            'Changes': [
                {
                    'Action': 'DELETE',
                    'ResourceRecordSet': {
                        'Name': record_name,
                        'Type': record_type,
                        'TTL': self.ttl,
                        'ResourceRecords': resource_records
                    }
                }
            ]
        }
        
        # Delete the record
        success, result = self.aws_operation_with_logging(
            service_name='route53',
            operation='change_resource_record_sets',
            with_result=True,
            HostedZoneId=hosted_zone.hosted_zone_id,
            ChangeBatch=change_batch
        )
        
        if not success:
            raise UserError(_("Failed to delete DNS record: %s") % result)
    
    @api.constrains('name')
    def _check_name(self):
        """
        Validate the record name.
        """
        for record in self:
            if record.name != '@':
                # Allow underscores in record names
                if not re.match(r'^[a-zA-Z0-9_][-a-zA-Z0-9_.]*$', record.name):
                    raise ValidationError(_("Record name '%s' contains invalid characters. Use only letters, numbers, hyphens, underscores and dots.") % record.name)
    
    @api.constrains('ttl')
    def _check_ttl(self):
        """
        Validate the TTL value.
        """
        for record in self:
            if record.ttl < 0:
                raise ValidationError(_("TTL cannot be negative."))
            if record.ttl > 604800:  # 7 days
                raise ValidationError(_("TTL cannot exceed 604800 seconds (7 days)."))
    
    @api.constrains('type', 'value')
    def _check_value_format(self):
        """
        Validate the value format based on record type.
        """
        for record in self:
            values = record.value.split(';')
            
            for value in values:
                value = value.strip()
                if not value:
                    continue
                    
                if record.type in ['A', 'AAAA']:
                    # IPv4/IPv6 validation could be more robust
                    if record.type == 'A' and not re.match(r'^(\d{1,3}\.){3}\d{1,3}$', value):
                        raise ValidationError(_("Invalid IPv4 address format for A record: %s") % value)
                
                elif record.type == 'CNAME':
                    if not value.endswith('.'):
                        raise ValidationError(_("CNAME record value must end with a dot: %s") % value)
                
                elif record.type == 'MX':
                    if not re.match(r'^\d+\s+\S+$', value):
                        raise ValidationError(_("MX record must have priority and hostname: %s") % value)
                
                elif record.type == 'SRV':
                    if not re.match(r'^\d+\s+\d+\s+\d+\s+\S+$', value):
                        raise ValidationError(_("SRV record must have priority, weight, port and hostname: %s") % value)
                        
                # More validations could be added for other record types