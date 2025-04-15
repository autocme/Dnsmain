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

# Mapping of geographic regions to AWS regions
# This helps determine the most appropriate AWS region based on a domain's geographic region
REGION_MAPPING = {
    # North America
    'us': 'us-east-1',
    'usa': 'us-east-1',
    'us-east': 'us-east-1',
    'us-west': 'us-west-2',
    'canada': 'ca-central-1',
    'mexico': 'us-east-1',
    'north america': 'us-east-1',
    
    # Europe
    'eu': 'eu-west-1',
    'europe': 'eu-west-1',
    'uk': 'eu-west-2',
    'britain': 'eu-west-2',
    'england': 'eu-west-2',
    'germany': 'eu-central-1',
    'france': 'eu-west-3',
    'spain': 'eu-south-2',
    'italy': 'eu-south-1',
    'sweden': 'eu-north-1',
    'ireland': 'eu-west-1',
    
    # Asia Pacific
    'asia': 'ap-southeast-1',
    'japan': 'ap-northeast-1',
    'india': 'ap-south-1',
    'australia': 'ap-southeast-2',
    'singapore': 'ap-southeast-1',
    'china': 'cn-north-1',
    'hong kong': 'ap-east-1',
    'korea': 'ap-northeast-2',
    
    # South America
    'south america': 'sa-east-1',
    'brazil': 'sa-east-1',
    
    # Middle East
    'middle east': 'me-south-1',
    'bahrain': 'me-south-1',
    'uae': 'me-central-1',
    
    # Africa
    'africa': 'af-south-1',
    'south africa': 'af-south-1',
}

class Route53Config(models.Model):
    _name = 'dns.route53.config'
    _description = 'AWS Route 53 Configuration'
    _inherit = ['dns.aws.client.mixin']

    name = fields.Char(string='Configuration Name', required=True)
    aws_credentials_id = fields.Many2one('dns.aws.credentials', string='AWS Credentials', required=True)
    aws_region = fields.Char(string='AWS Region', required=True, default='us-east-1')
    active = fields.Boolean(default=True)
    
    # Fields for backward compatibility and convenience
    aws_access_key_id = fields.Char(related='aws_credentials_id.aws_access_key_id', string='AWS Access Key ID', readonly=True)
    aws_secret_access_key = fields.Char(related='aws_credentials_id.aws_secret_access_key', string='AWS Secret Access Key', readonly=True)
    
    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'Configuration name must be unique!')
    ]
    
    def _get_route53_client(self):
        """Create and return a boto3 Route 53 client"""
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
        Get the appropriate AWS region based on a geographic region string.
        If no match is found, returns the default (us-east-1)
        """
        if not geographic_region:
            return 'us-east-1'
            
        # Normalize the geographic region for matching
        geo_region = geographic_region.lower().strip()
        
        # Direct lookup in the mapping
        if geo_region in REGION_MAPPING:
            return REGION_MAPPING[geo_region]
            
        # Try partial matching if direct lookup fails
        for region_key, aws_region in REGION_MAPPING.items():
            if region_key in geo_region or geo_region in region_key:
                return aws_region
                
        # Default to us-east-1 if no match is found
        return 'us-east-1'
        
    @api.model
    def create_config_for_region(self, region, aws_credentials_id):
        """
        Create or find a Route53 configuration for a specific geographic region.
        Returns the configuration record.
        """
        # Check if a configuration already exists for the region
        aws_region = self.get_aws_region_for_geographic_region(region)
        existing_config = self.search([
            ('aws_region', '=', aws_region),
            ('aws_credentials_id', '=', aws_credentials_id.id if hasattr(aws_credentials_id, 'id') else aws_credentials_id),
            ('active', '=', True)
        ], limit=1)
        
        if existing_config:
            return existing_config
            
        # Create a new configuration with region-specific naming
        region_display = region or 'Default'
        config_name = f"AWS Route53 - {region_display}"
        
        return self.create({
            'name': config_name,
            'aws_credentials_id': aws_credentials_id.id if hasattr(aws_credentials_id, 'id') else aws_credentials_id,
            'aws_region': aws_region,
            'active': True
        })