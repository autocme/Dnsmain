# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
#
# Copyright (C) 2023 JAAH

import logging
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import boto3
from botocore.exceptions import ClientError

_logger = logging.getLogger(__name__)

class Domain(models.Model):
    _inherit = ['dns.domain', 'dns.aws.client.mixin']
    _name = 'dns.domain'
    
    route53_config_id = fields.Many2one('dns.route53.config', string='Route 53 Configuration')
    route53_hosted_zone_id = fields.Char(string='Route 53 Hosted Zone ID', help='If empty, we will try to find it automatically')
    route53_sync = fields.Boolean(string='Sync with Route 53', default=False)
    route53_auto_region_sync = fields.Boolean(string='Auto-sync Region', default=True, 
                                             help='Automatically select the best AWS region based on the domain geographic region')
    route53_sync_status = fields.Selection([
        ('not_synced', 'Not Synced'),
        ('synced', 'Synced'),
        ('error', 'Error')
    ], string='Route 53 Sync Status', compute='_compute_route53_sync_status', store=True)
    route53_last_sync = fields.Datetime(string='Last Route 53 Sync')
    route53_error_message = fields.Text(string='Route 53 Error Message')
    aws_credentials_id = fields.Many2one('dns.aws.credentials', string='AWS Credentials', 
                                         help='AWS credentials to use for this domain')
    
    @api.depends('route53_sync', 'route53_config_id', 'route53_last_sync', 'route53_error_message')
    def _compute_route53_sync_status(self):
        for domain in self:
            if not domain.route53_sync or not domain.route53_config_id:
                domain.route53_sync_status = 'not_synced'
            elif domain.route53_error_message:
                domain.route53_sync_status = 'error'
            elif domain.route53_last_sync:
                domain.route53_sync_status = 'synced'
            else:
                domain.route53_sync_status = 'not_synced'
    
    @api.onchange('region', 'route53_auto_region_sync', 'aws_credentials_id')
    def _onchange_region_for_route53(self):
        """Update Route53 configuration based on the domain's geographic region"""
        if self.region and self.route53_auto_region_sync and self.aws_credentials_id:
            try:
                # Get or create a configuration for this region
                Route53Config = self.env['dns.route53.config']
                config = Route53Config.create_config_for_region(
                    self.region, 
                    self.aws_credentials_id
                )
                
                # Set the configuration for this domain
                self.route53_config_id = config.id
                
                # Now try to find the hosted zone ID
                if self.name and not self.route53_hosted_zone_id:
                    hosted_zone_id = config.get_hosted_zone_id_by_domain(self.name)
                    if hosted_zone_id:
                        self.route53_hosted_zone_id = hosted_zone_id
                        
            except Exception as e:
                _logger.error("Error syncing AWS region: %s", str(e))
                # Don't raise error in onchange, just log it
    
    @api.onchange('route53_config_id', 'name')
    def _onchange_route53_config(self):
        if self.route53_config_id and self.name and not self.route53_hosted_zone_id:
            try:
                config = self.route53_config_id
                hosted_zone_id = config.get_hosted_zone_id_by_domain(self.name)
                if hosted_zone_id:
                    self.route53_hosted_zone_id = hosted_zone_id
            except Exception as e:
                _logger.error("Error getting hosted zone ID: %s", str(e))
                # Don't raise error in onchange, just log it
    
    def sync_all_subdomains_to_route53(self):
        """Sync all subdomains for this domain to Route 53"""
        self.ensure_one()
        
        if not self.route53_sync:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sync Disabled'),
                    'message': _('Route 53 sync is disabled for this domain.'),
                    'sticky': False,
                    'type': 'warning',
                }
            }
            
        if not self.route53_config_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Config Missing'),
                    'message': _('Please select a Route 53 configuration for this domain.'),
                    'sticky': False,
                    'type': 'warning',
                }
            }
            
        if not self.route53_hosted_zone_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Hosted Zone Missing'),
                    'message': _('No hosted zone ID specified or found for this domain.'),
                    'sticky': False,
                    'type': 'warning',
                }
            }
        
        try:
            # Trigger sync for all DNS records
            for dns_record in self.subdomain_ids:
                dns_record.sync_to_route53()
                
            self.write({
                'route53_last_sync': fields.Datetime.now(),
                'route53_error_message': False,
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sync Complete'),
                    'message': _('All DNS records have been synchronized with Route 53.'),
                    'sticky': False,
                    'type': 'success',
                }
            }
        except Exception as e:
            error_message = str(e)
            _logger.error("Route 53 sync error: %s", error_message)
            
            self.write({
                'route53_error_message': error_message,
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sync Error'),
                    'message': error_message,
                    'sticky': False,
                    'type': 'danger',
                }
            }
            
    def sync_route53_records_from_aws(self):
        """Sync DNS records from AWS Route 53 to Odoo DNS records for this domain"""
        self.ensure_one()
        
        if not self.route53_sync:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sync Disabled'),
                    'message': _('Route 53 sync is disabled for this domain.'),
                    'sticky': False,
                    'type': 'warning',
                }
            }
            
        if not self.route53_config_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Config Missing'),
                    'message': _('Please select a Route 53 configuration for this domain.'),
                    'sticky': False,
                    'type': 'warning',
                }
            }
            
        if not self.route53_hosted_zone_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Hosted Zone Missing'),
                    'message': _('No hosted zone ID specified or found for this domain.'),
                    'sticky': False,
                    'type': 'warning',
                }
            }
        
        try:
            # Call the sync method in DNS record model
            DNSRecord = self.env['dns.subdomain']
            result = DNSRecord.sync_route53_records(domain_id=self.id)
            
            # Update last sync timestamp
            self.write({
                'route53_last_sync': fields.Datetime.now(),
                'route53_error_message': False,
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sync Complete'),
                    'message': _('DNS records have been synchronized from Route 53.'),
                    'sticky': False,
                    'type': 'success',
                }
            }
        except Exception as e:
            error_message = str(e)
            _logger.error("Route 53 sync error: %s", error_message)
            
            self.write({
                'route53_error_message': error_message,
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sync Error'),
                    'message': error_message,
                    'sticky': False,
                    'type': 'danger',
                }
            }
    
    def sync_all_route53_records_from_aws(self):
        """
        Action called by the 'Sync Domain Records from Route 53' button.
        This method is the same as sync_route53_records_from_aws but is used for the server action.
        """
        return self.sync_route53_records_from_aws()
    
    @api.model
    def sync_route53_hosted_zones(self):
        """
        Sync all AWS Route 53 hosted zones to Odoo domains
        This creates domain records in Odoo for any hosted zones found in Route 53
        that don't already exist.
        """
        # Get all active Route 53 configurations
        Route53Config = self.env['dns.route53.config']
        configs = Route53Config.search([('active', '=', True)])
        
        if not configs:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No Configurations'),
                    'message': _('No active Route 53 configurations found.'),
                    'sticky': False,
                    'type': 'warning',
                }
            }
        
        domain_count = 0
        error_messages = []
        
        for config in configs:
            try:
                # Get all hosted zones from this config
                hosted_zones = config.get_hosted_zones()
                
                for zone in hosted_zones:
                    # Extract domain name from zone name (remove trailing dot)
                    domain_name = zone['Name'].rstrip('.')
                    zone_id = zone['Id'].split('/')[-1]  # Extract ID from path
                    
                    # Check if domain already exists
                    existing_domain = self.search([
                        ('name', '=', domain_name)
                    ], limit=1)
                    
                    if not existing_domain:
                        # Create the domain in Odoo
                        new_domain = self.create({
                            'name': domain_name,
                            'route53_sync': True,
                            'route53_config_id': config.id,
                            'route53_hosted_zone_id': zone_id,
                            'route53_last_sync': fields.Datetime.now(),
                        })
                        domain_count += 1
                    elif not existing_domain.route53_hosted_zone_id:
                        # Update existing domain with Route 53 info
                        existing_domain.write({
                            'route53_sync': True,
                            'route53_config_id': config.id,
                            'route53_hosted_zone_id': zone_id,
                            'route53_last_sync': fields.Datetime.now(),
                        })
                        domain_count += 1
            
            except Exception as e:
                error_message = f"Error with config '{config.name}': {str(e)}"
                _logger.error(error_message)
                error_messages.append(error_message)
        
        # Generate response message
        if error_messages:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sync Completed With Errors'),
                    'message': _(f"Created/updated {domain_count} domains. Errors: {'; '.join(error_messages)}"),
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
                    'message': _(f"Successfully created/updated {domain_count} domains from Route 53 hosted zones."),
                    'sticky': False,
                    'type': 'success',
                }
            }