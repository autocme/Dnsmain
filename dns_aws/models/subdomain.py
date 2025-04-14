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
            
            # Prepare record parameters based on conversion method (A or CNAME)
            record_type = 'A' if self.conversion_method == 'a' else 'CNAME'
            record_value = self.value
            
            # If CNAME, ensure value ends with a dot
            if record_type == 'CNAME' and not record_value.endswith('.'):
                record_value = record_value + '.'
                
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
                                'TTL': 300,
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
        if any(field in vals for field in ['name', 'domain_id', 'conversion_method', 'value']):
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
                    
                    # Delete Route 53 record
                    record_type = 'A' if record.conversion_method == 'a' else 'CNAME'
                    record_value = record.value
                    
                    # If CNAME, ensure value ends with a dot
                    if record_type == 'CNAME' and not record_value.endswith('.'):
                        record_value = record_value + '.'
                    
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
                                        'TTL': 300,
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