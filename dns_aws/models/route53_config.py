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

# Route 53 is a global service, so we don't need region mapping
# We keep the standard global endpoint region (us-east-1) for API calls
GLOBAL_REGION = 'us-east-1'

class Route53Config(models.Model):
    _name = 'dns.route53.config'
    _description = 'AWS Route 53 Configuration'
    _inherit = ['dns.aws.client.mixin']

    name = fields.Char(string='Configuration Name', required=True)
    aws_credentials_id = fields.Many2one('dns.aws.credentials', string='AWS Credentials', required=True)
    aws_region = fields.Char(string='AWS Region', readonly=True, required=True, default=GLOBAL_REGION, 
                          help='Route 53 is a global AWS service and always uses the us-east-1 endpoint, regardless of your geographic location')
    active = fields.Boolean(default=True)
    
    # Fields for backward compatibility and convenience
    aws_access_key_id = fields.Char(related='aws_credentials_id.aws_access_key_id', string='AWS Access Key ID', readonly=True)
    aws_secret_access_key = fields.Char(related='aws_credentials_id.aws_secret_access_key', string='AWS Secret Access Key', readonly=True)
    
    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'Configuration name must be unique!')
    ]
    
    def _get_route53_client(self):
        """
        Create and return a boto3 Route 53 client
        
        Route 53 is a global service that always uses us-east-1 region,
        regardless of the region specified in the aws_region field.
        """
        try:
            if not self.aws_credentials_id:
                raise ValidationError(_("AWS credentials are required to create a Route 53 client"))
                
            # Use the AWS client mixin to create the client
            return self._get_boto3_client('route53')
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
        
    @api.model
    def get_aws_region_for_geographic_region(self, geographic_region):
        """
        Route 53 is a global service, so we always return the global endpoint region
        regardless of the geographic region passed
        """
        # Always return the global endpoint region for Route 53
        return GLOBAL_REGION
        
    @api.model
    def create_config_for_region(self, region, aws_credentials_id):
        """
        Create or find a Route53 configuration for the given credentials.
        Route 53 is a global service, so we no longer need region-specific configurations.
        Returns the configuration record.
        """
        # Check if a configuration already exists for these credentials
        existing_config = self.search([
            ('aws_credentials_id', '=', aws_credentials_id.id if hasattr(aws_credentials_id, 'id') else aws_credentials_id),
            ('active', '=', True)
        ], limit=1)
        
        if existing_config:
            return existing_config
            
        # Create a new global configuration (region is always global for Route 53)
        config_name = "AWS Route53 - Global Service"
        
        return self.create({
            'name': config_name,
            'aws_credentials_id': aws_credentials_id.id if hasattr(aws_credentials_id, 'id') else aws_credentials_id,
            'aws_region': GLOBAL_REGION,
            'active': True
        })