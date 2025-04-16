# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
#
# Copyright (C) 2023 JAAH

import logging
import re
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from botocore.exceptions import ClientError
import boto3

_logger = logging.getLogger(__name__)

class AWSUtils(models.AbstractModel):
    _name = 'dns.aws.utils'
    _description = 'AWS Utilities'
    
    @api.model
    def get_default_aws_credentials(self):
        """
        Get default AWS credentials from system parameters
        
        Returns:
            A dns.aws.credentials record or False if not found
        """
        IrParam = self.env['ir.config_parameter'].sudo()
        default_creds_id = IrParam.get_param('dns_aws.default_credentials_id')
        
        if default_creds_id and default_creds_id.isdigit():
            return self.env['dns.aws.credentials'].browse(int(default_creds_id)).exists()
        
        return self.env['dns.aws.credentials']  # Empty recordset
    
    @api.model
    def get_default_aws_region(self):
        """
        Get default AWS region from system parameters
        
        Returns:
            The default AWS region as a string
            
        Note:
            This region is only used for regional AWS services.
            Global AWS services like Route53 always use the global endpoint (us-east-1),
            regardless of this setting.
        """
        return self.env['ir.config_parameter'].sudo().get_param('dns_aws.default_aws_region', 'us-east-1')
    
    @api.model
    def test_aws_credentials(self, aws_access_key_id, aws_secret_access_key, region_name='us-east-1'):
        """
        Test if AWS credentials are valid by making a simple AWS API call
        
        Args:
            aws_access_key_id: AWS access key ID
            aws_secret_access_key: AWS secret access key
            region_name: AWS region name (ignored for IAM which is a global service)
            
        Returns:
            A dict with 'success' and 'message' keys
            
        Note:
            This method uses the IAM service which is a global AWS service.
            The region_name parameter is ignored since IAM always uses the global endpoint.
        """
        if not aws_access_key_id or not aws_secret_access_key:
            return {
                'success': False,
                'message': _("AWS credentials are not provided.")
            }
        
        try:
            # Create a client for the IAM service (typically has the least restrictive permissions)
            # IAM is a global service, so we always use the global endpoint (us-east-1)
            client = boto3.client(
                'iam',
                aws_access_key_id=aws_access_key_id,
                aws_secret_access_key=aws_secret_access_key,
                region_name='us-east-1'  # Global endpoint for IAM
            )
            
            # Try to get the current user
            response = client.get_user()
            
            # If we get here, credentials are valid
            return {
                'success': True,
                'message': _("AWS credentials are valid."),
                'user': response.get('User', {}).get('UserName', '')
            }
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            
            # Special case: if the error is AccessDenied but it's because the user doesn't have
            # permission to call GetUser, the credentials might still be valid
            if error_code == 'AccessDenied' and 'not authorized to perform: iam:GetUser' in error_message:
                return {
                    'success': True,
                    'message': _("AWS credentials appear valid, but have limited permissions."),
                    'user': ''
                }
                
            # Otherwise, credentials are invalid or have other issues
            return {
                'success': False,
                'message': f"{error_code}: {error_message}"
            }
        except Exception as e:
            return {
                'success': False,
                'message': str(e)
            }
    
    @api.model
    def paginate_aws_results(self, client, method_name, result_key, **kwargs):
        """
        Paginate AWS API results to handle large result sets
        
        Args:
            client: A boto3 client
            method_name: The name of the method to call on the client
            result_key: The key in the response that contains the results
            **kwargs: Additional arguments to pass to the method
            
        Returns:
            A list of all results from all pages
        """
        method = getattr(client, method_name)
        paginator = client.get_paginator(method_name)
        
        results = []
        try:
            for page in paginator.paginate(**kwargs):
                if result_key in page:
                    results.extend(page[result_key])
        except Exception as e:
            _logger.error("Error during AWS pagination: %s", str(e))
            raise ValidationError(_("Error during AWS pagination: %s") % str(e))
            
        return results
    
    @api.model
    def get_aws_service_regions(self, service_name, credentials=None):
        """
        Get available regions for an AWS service
        
        Args:
            service_name: The name of the AWS service
            credentials: Optional AWS credentials dict
            
        Returns:
            A list of available regions for the service
        """
        # Use provided credentials or get default credentials
        if not credentials:
            default_creds = self.get_default_aws_credentials()
            if default_creds:
                credentials = {
                    'aws_access_key_id': default_creds.aws_access_key_id,
                    'aws_secret_access_key': default_creds.aws_secret_access_key,
                }
            else:
                IrParam = self.env['ir.config_parameter'].sudo()
                credentials = {
                    'aws_access_key_id': IrParam.get_param('dns_aws.default_aws_access_key_id', ''),
                    'aws_secret_access_key': IrParam.get_param('dns_aws.default_aws_secret_access_key', ''),
                }
        
        # Validate credentials
        if not credentials.get('aws_access_key_id') or not credentials.get('aws_secret_access_key'):
            raise ValidationError(_("AWS credentials are not properly configured."))
        
        try:
            # Create a session with the provided credentials
            session = boto3.Session(
                aws_access_key_id=credentials['aws_access_key_id'],
                aws_secret_access_key=credentials['aws_secret_access_key'],
            )
            
            # Get regions for the service
            regions = session.get_available_regions(service_name)
            return sorted(regions)
        except Exception as e:
            _logger.error("Error getting AWS regions for service %s: %s", service_name, str(e))
            raise ValidationError(_("Error getting AWS regions for service %s: %s") % (service_name, str(e)))
    
    @api.model
    def get_route53_record_sets(self, hosted_zone_id, credentials=None, region_name=None):
        """
        Get all record sets for a Route 53 hosted zone
        
        Args:
            hosted_zone_id: Route 53 hosted zone ID
            credentials: Optional AWS credentials dict
            region_name: Optional AWS region name (ignored as Route53 is a global service)
            
        Returns:
            A list of record sets
            
        Note:
            Route53 is a global service, so the region_name parameter is ignored.
            The AWS global endpoint (us-east-1) is always used regardless of this parameter.
        """
        # Use provided credentials or get default credentials
        if not credentials:
            default_creds = self.get_default_aws_credentials()
            if default_creds:
                credentials = {
                    'aws_access_key_id': default_creds.aws_access_key_id,
                    'aws_secret_access_key': default_creds.aws_secret_access_key,
                }
            else:
                IrParam = self.env['ir.config_parameter'].sudo()
                credentials = {
                    'aws_access_key_id': IrParam.get_param('dns_aws.default_aws_access_key_id', ''),
                    'aws_secret_access_key': IrParam.get_param('dns_aws.default_aws_secret_access_key', ''),
                }
        
        # Use provided region or get default region
        if not region_name:
            region_name = self.get_default_aws_region()
            
        # Validate hosted zone ID
        if not hosted_zone_id:
            raise ValidationError(_("Hosted zone ID is required."))
            
        # If the hosted zone ID includes the /hostedzone/ prefix, remove it
        if hosted_zone_id.startswith('/hostedzone/'):
            hosted_zone_id = hosted_zone_id.split('/hostedzone/')[1]
            
        try:
            # Create a Route 53 client - always use the global endpoint region (us-east-1)
            # Ignoring the region_name parameter as Route53 is a global service
            client = boto3.client(
                'route53',
                aws_access_key_id=credentials['aws_access_key_id'],
                aws_secret_access_key=credentials['aws_secret_access_key'],
                region_name='us-east-1'  # Global endpoint for Route53
            )
            
            # Use pagination to get all record sets
            return self.paginate_aws_results(
                client=client,
                method_name='list_resource_record_sets',
                result_key='ResourceRecordSets',
                HostedZoneId=hosted_zone_id
            )
        except Exception as e:
            _logger.error("Error getting Route 53 record sets: %s", str(e))
            raise ValidationError(_("Error getting Route 53 record sets: %s") % str(e))
            
    @api.model
    def normalize_route53_record_type(self, record_type):
        """
        Normalize Route 53 record type to standard format (uppercase)
        
        Args:
            record_type: Record type string (e.g., 'a', 'CNAME', 'mx')
            
        Returns:
            Normalized record type (uppercase)
        """
        if not record_type:
            return ''
            
        return record_type.upper()
        
    @api.model
    def normalize_route53_record_name(self, record_name, zone_name):
        """
        Normalize Route 53 record name by removing the trailing dot and zone name
        
        Args:
            record_name: Record name from Route 53 (e.g., 'www.example.com.')
            zone_name: Zone name (e.g., 'example.com')
            
        Returns:
            Normalized record name (e.g., 'www' or '@' for the root domain)
        """
        if not record_name:
            return '@'
            
        # Remove trailing dot
        name = record_name.rstrip('.')
        
        # If the name is the same as the zone name, it's the root domain
        if name == zone_name.rstrip('.'):
            return '@'
            
        # Otherwise, remove the zone name suffix
        zone_suffix = '.' + zone_name.rstrip('.')
        if name.endswith(zone_suffix):
            name = name[:-len(zone_suffix)]
            
        return name
        
    @api.model
    def format_route53_record_value(self, record_set):
        """
        Format Route 53 record value(s) into a string
        
        Args:
            record_set: A Route 53 record set dict
            
        Returns:
            Formatted record value as a string
        """
        record_type = record_set.get('Type', '')
        
        # For records with ResourceRecords
        if 'ResourceRecords' in record_set:
            records = record_set['ResourceRecords']
            values = [r.get('Value', '') for r in records]
            
            # Format based on record type
            if record_type == 'MX':
                # MX records: "10 mail.example.com"
                return '\n'.join(values)
            elif record_type == 'TXT':
                # TXT records: strip quotes
                return '\n'.join([v.strip('"') for v in values])
            else:
                # Other record types: join values with newlines
                return '\n'.join(values)
                
        # For alias records
        elif 'AliasTarget' in record_set:
            alias = record_set['AliasTarget']
            return f"ALIAS {alias.get('DNSName', '')}"
            
        # Default: empty string
        return ''