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

class Route53Config(models.Model):
    _name = 'dns.route53.config'
    _description = 'AWS Route 53 Configuration'

    name = fields.Char(string='Configuration Name', required=True)
    aws_access_key_id = fields.Char(string='AWS Access Key ID', required=True)
    aws_secret_access_key = fields.Char(string='AWS Secret Access Key', required=True)
    aws_region = fields.Char(string='AWS Region', required=True, default='us-east-1')
    active = fields.Boolean(default=True)
    
    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'Configuration name must be unique!')
    ]
    
    def _get_route53_client(self):
        """Create and return a boto3 Route 53 client"""
        try:
            client = boto3.client(
                'route53',
                aws_access_key_id=self.aws_access_key_id,
                aws_secret_access_key=self.aws_secret_access_key,
                region_name=self.aws_region
            )
            return client
        except Exception as e:
            _logger.error("Failed to create Route 53 client: %s", str(e))
            raise ValidationError(_("Failed to create Route 53 client: %s") % str(e))
    
    def test_connection(self):
        """Test the connection to AWS Route 53"""
        try:
            client = self._get_route53_client()
            # Try to list hosted zones to test connection
            response = client.list_hosted_zones(MaxItems='1')
            
            # If we get here, connection is successful
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Connection Test Successful'),
                    'message': _('Successfully connected to AWS Route 53.'),
                    'sticky': False,
                    'type': 'success',
                }
            }
        except ClientError as e:
            _logger.error("AWS Route 53 connection test failed: %s", str(e))
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Connection Test Failed'),
                    'message': str(e),
                    'sticky': False,
                    'type': 'danger',
                }
            }
    
    def get_hosted_zones(self):
        """Get list of hosted zones from Route 53"""
        client = self._get_route53_client()
        try:
            response = client.list_hosted_zones()
            return response.get('HostedZones', [])
        except ClientError as e:
            _logger.error("Failed to get hosted zones: %s", str(e))
            raise ValidationError(_("Failed to get hosted zones: %s") % str(e))
    
    def get_hosted_zone_id_by_domain(self, domain_name):
        """Find hosted zone ID for a domain name"""
        hosted_zones = self.get_hosted_zones()
        
        # Remove trailing dot from hosted zone names
        for zone in hosted_zones:
            zone_name = zone['Name'].rstrip('.')
            if domain_name.endswith(zone_name):
                return zone['Id'].split('/')[-1]  # Extract ID from path
        
        return None