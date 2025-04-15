# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
#
# Copyright (C) 2023 JAAH

import json
import logging
import re
import boto3
import botocore
from odoo import api, fields, models, _, tools
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class AWSUtils(models.AbstractModel):
    """
    Utility model for AWS-related operations.
    Provides static helper methods that can be used by any module.
    """
    _name = 'aws.utils'
    _description = 'AWS Utilities'
    
    @api.model
    def get_all_aws_regions(self):
        """
        Get a list of all available AWS regions.
        
        Returns:
            List of region dictionaries with 'code' and 'name' keys
        """
        # Try to get regions from AWS if possible
        try:
            # Use default credentials (can be EC2 instance profile in production)
            session = boto3.Session()
            ec2_client = session.client('ec2')
            regions = ec2_client.describe_regions()
            return [
                {'code': region['RegionName'], 'name': self._get_region_display_name(region['RegionName'])}
                for region in regions['Regions']
            ]
        except Exception:
            # Fallback to hardcoded list
            return [
                {'code': 'us-east-1', 'name': 'US East (N. Virginia)'},
                {'code': 'us-east-2', 'name': 'US East (Ohio)'},
                {'code': 'us-west-1', 'name': 'US West (N. California)'},
                {'code': 'us-west-2', 'name': 'US West (Oregon)'},
                {'code': 'af-south-1', 'name': 'Africa (Cape Town)'},
                {'code': 'ap-east-1', 'name': 'Asia Pacific (Hong Kong)'},
                {'code': 'ap-south-1', 'name': 'Asia Pacific (Mumbai)'},
                {'code': 'ap-northeast-3', 'name': 'Asia Pacific (Osaka)'},
                {'code': 'ap-northeast-2', 'name': 'Asia Pacific (Seoul)'},
                {'code': 'ap-southeast-1', 'name': 'Asia Pacific (Singapore)'},
                {'code': 'ap-southeast-2', 'name': 'Asia Pacific (Sydney)'},
                {'code': 'ap-northeast-1', 'name': 'Asia Pacific (Tokyo)'},
                {'code': 'ca-central-1', 'name': 'Canada (Central)'},
                {'code': 'eu-central-1', 'name': 'Europe (Frankfurt)'},
                {'code': 'eu-west-1', 'name': 'Europe (Ireland)'},
                {'code': 'eu-west-2', 'name': 'Europe (London)'},
                {'code': 'eu-south-1', 'name': 'Europe (Milan)'},
                {'code': 'eu-west-3', 'name': 'Europe (Paris)'},
                {'code': 'eu-north-1', 'name': 'Europe (Stockholm)'},
                {'code': 'me-south-1', 'name': 'Middle East (Bahrain)'},
                {'code': 'sa-east-1', 'name': 'South America (São Paulo)'}
            ]
    
    @api.model
    def _get_region_display_name(self, region_code):
        """
        Convert a region code to a human-readable name.
        
        Args:
            region_code: AWS region code (e.g., 'us-east-1')
            
        Returns:
            Human-readable region name
        """
        region_names = {
            'us-east-1': 'US East (N. Virginia)',
            'us-east-2': 'US East (Ohio)',
            'us-west-1': 'US West (N. California)',
            'us-west-2': 'US West (Oregon)',
            'af-south-1': 'Africa (Cape Town)',
            'ap-east-1': 'Asia Pacific (Hong Kong)',
            'ap-south-1': 'Asia Pacific (Mumbai)',
            'ap-northeast-3': 'Asia Pacific (Osaka)',
            'ap-northeast-2': 'Asia Pacific (Seoul)',
            'ap-southeast-1': 'Asia Pacific (Singapore)',
            'ap-southeast-2': 'Asia Pacific (Sydney)',
            'ap-northeast-1': 'Asia Pacific (Tokyo)',
            'ca-central-1': 'Canada (Central)',
            'eu-central-1': 'Europe (Frankfurt)',
            'eu-west-1': 'Europe (Ireland)',
            'eu-west-2': 'Europe (London)',
            'eu-south-1': 'Europe (Milan)',
            'eu-west-3': 'Europe (Paris)',
            'eu-north-1': 'Europe (Stockholm)',
            'me-south-1': 'Middle East (Bahrain)',
            'sa-east-1': 'South America (São Paulo)'
        }
        return region_names.get(region_code, region_code)
    
    @api.model
    def get_best_region_for_geographic_location(self, geographic_location):
        """
        Get the most appropriate AWS region for a geographic location.
        
        Args:
            geographic_location: Geographic region name or country code
            
        Returns:
            Most appropriate AWS region code
        """
        if not geographic_location:
            return 'us-east-1'  # Default region
            
        # Normalize the input
        location = geographic_location.lower().strip()
        
        # Map of geographic regions to AWS regions
        region_map = {
            # North America
            'us': 'us-east-1',
            'usa': 'us-east-1',
            'united states': 'us-east-1',
            'america': 'us-east-1',
            'north america': 'us-east-1',
            'canada': 'ca-central-1',
            'mexico': 'us-west-2',
            
            # South America
            'brazil': 'sa-east-1',
            'south america': 'sa-east-1',
            'latin america': 'sa-east-1',
            
            # Europe
            'europe': 'eu-west-1',
            'eu': 'eu-west-1',
            'ireland': 'eu-west-1',
            'uk': 'eu-west-2',
            'united kingdom': 'eu-west-2',
            'england': 'eu-west-2',
            'britain': 'eu-west-2',
            'germany': 'eu-central-1',
            'france': 'eu-west-3',
            'italy': 'eu-south-1',
            'spain': 'eu-west-3',
            'sweden': 'eu-north-1',
            'norway': 'eu-north-1',
            'finland': 'eu-north-1',
            'denmark': 'eu-north-1',
            
            # Asia Pacific
            'asia': 'ap-southeast-1',
            'india': 'ap-south-1',
            'japan': 'ap-northeast-1',
            'australia': 'ap-southeast-2',
            'singapore': 'ap-southeast-1',
            'hong kong': 'ap-east-1',
            'korea': 'ap-northeast-2',
            'south korea': 'ap-northeast-2',
            'china': 'cn-north-1',
            
            # Middle East
            'middle east': 'me-south-1',
            'bahrain': 'me-south-1',
            'uae': 'me-south-1',
            'united arab emirates': 'me-south-1',
            
            # Africa
            'africa': 'af-south-1',
            'south africa': 'af-south-1',
        }
        
        # Check direct matches first
        if location in region_map:
            return region_map[location]
            
        # Check for partial matches
        for key, region in region_map.items():
            if key in location or location in key:
                return region
                
        # Default to US East
        return 'us-east-1'
    
    @api.model
    def format_aws_arn(self, service, resource, region=None, account_id=None, partition='aws'):
        """
        Format an AWS ARN (Amazon Resource Name).
        
        Args:
            service: AWS service (e.g., 's3', 'ec2')
            resource: Resource identifier
            region: Optional AWS region
            account_id: Optional AWS account ID
            partition: AWS partition (default: 'aws')
            
        Returns:
            Formatted ARN string
        """
        arn = f"arn:{partition}:{service}:"
        
        if region:
            arn += f"{region}:"
            
        if account_id:
            arn += f"{account_id}:"
        
        arn += resource
        return arn
    
    @api.model
    def parse_aws_arn(self, arn):
        """
        Parse an AWS ARN into its components.
        
        Args:
            arn: AWS ARN to parse
            
        Returns:
            Dictionary with ARN components
        """
        if not arn:
            return {}
            
        # ARN format: arn:partition:service:region:account-id:resource
        parts = arn.split(':', 5)
        if len(parts) < 6 or parts[0] != 'arn':
            return {}
            
        return {
            'partition': parts[1],
            'service': parts[2],
            'region': parts[3],
            'account_id': parts[4],
            'resource': parts[5]
        }
    
    @api.model
    def get_aws_vpc_information(self, vpc_id, region=None, aws_credentials_id=None):
        """
        Get information about an AWS VPC.
        
        Args:
            vpc_id: VPC ID to query
            region: Optional AWS region
            aws_credentials_id: Optional AWS credentials ID
            
        Returns:
            Dictionary with VPC information
        """
        # Get AWS credentials
        credentials = None
        if aws_credentials_id:
            credentials = self.env['aws.credentials'].browse(aws_credentials_id)
            if not credentials.exists():
                credentials = None
                
        if not credentials:
            credentials = self.env['aws.credentials'].get_default_credentials()
            
        if not credentials:
            raise UserError(_('No AWS credentials found.'))
            
        # Get EC2 client
        client = credentials.get_client('ec2', region_name=region)
        
        # Get VPC information
        response = client.describe_vpcs(VpcIds=[vpc_id])
        
        if 'Vpcs' not in response or not response['Vpcs']:
            return {}
            
        vpc = response['Vpcs'][0]
        
        # Get subnet information
        subnets_response = client.describe_subnets(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])
        subnets = subnets_response.get('Subnets', [])
        
        # Get security group information
        sg_response = client.describe_security_groups(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])
        security_groups = sg_response.get('SecurityGroups', [])
        
        # Format response
        result = {
            'vpc_id': vpc['VpcId'],
            'state': vpc.get('State', ''),
            'cidr_block': vpc.get('CidrBlock', ''),
            'is_default': vpc.get('IsDefault', False),
            'tags': vpc.get('Tags', []),
            'subnets': [
                {
                    'subnet_id': subnet['SubnetId'],
                    'cidr_block': subnet.get('CidrBlock', ''),
                    'availability_zone': subnet.get('AvailabilityZone', ''),
                    'available_ip_address_count': subnet.get('AvailableIpAddressCount', 0)
                }
                for subnet in subnets
            ],
            'security_groups': [
                {
                    'group_id': sg['GroupId'],
                    'group_name': sg.get('GroupName', ''),
                    'description': sg.get('Description', '')
                }
                for sg in security_groups
            ]
        }
        
        return result
    
    @api.model
    def validate_aws_resource_name(self, name, resource_type=None):
        """
        Validate an AWS resource name according to AWS naming rules.
        
        Args:
            name: Resource name to validate
            resource_type: Optional resource type for specific validation
            
        Returns:
            (bool, str) tuple with (is_valid, message)
        """
        if not name:
            return False, _("Resource name cannot be empty")
            
        # General validation rules
        if len(name) > 255:
            return False, _("Resource name cannot exceed 255 characters")
            
        # Resource-specific validation
        if resource_type == 's3_bucket':
            # S3 bucket naming rules
            if len(name) < 3:
                return False, _("S3 bucket names must be at least 3 characters long")
            if len(name) > 63:
                return False, _("S3 bucket names cannot exceed 63 characters")
            if not re.match(r'^[a-z0-9][-a-z0-9.]*[a-z0-9]$', name):
                return False, _("S3 bucket names can only contain lowercase letters, numbers, hyphens, and periods")
            if '..' in name:
                return False, _("S3 bucket names cannot contain two adjacent periods")
            if re.match(r'^[0-9.]+$', name):
                return False, _("S3 bucket names cannot be formatted as an IP address")
            if name.startswith('xn--') or name.startswith('sthree-'):
                return False, _("S3 bucket names cannot start with the prefix 'xn--' or 'sthree-'")
                
        elif resource_type == 'lambda_function':
            # Lambda function naming rules
            if not re.match(r'^[a-zA-Z0-9-_]+$', name):
                return False, _("Lambda function names can only contain letters, numbers, hyphens, and underscores")
                
        elif resource_type == 'dynamodb_table':
            # DynamoDB table naming rules
            if len(name) < 3:
                return False, _("DynamoDB table names must be at least 3 characters long")
            if len(name) > 255:
                return False, _("DynamoDB table names cannot exceed 255 characters")
            if not re.match(r'^[a-zA-Z0-9_.-]+$', name):
                return False, _("DynamoDB table names can only contain letters, numbers, underscores, hyphens, and periods")
                
        elif resource_type == 'route53_domain':
            # Domain naming rules
            if not re.match(r'^[a-z0-9][-a-z0-9.]*[a-z0-9]$', name):
                return False, _("Domain names can only contain lowercase letters, numbers, hyphens, and periods")
                
        # Valid if no specific rules violated
        return True, ""
    
    @api.model
    def cleanup_aws_tags(self, tags):
        """
        Clean up and validate AWS resource tags.
        
        Args:
            tags: Dictionary of tags or list of tag dictionaries
            
        Returns:
            Properly formatted list of tag dictionaries
        """
        result = []
        
        # Convert dict to list format if needed
        if isinstance(tags, dict):
            tags = [{'Key': k, 'Value': v} for k, v in tags.items()]
            
        # Process each tag
        for tag in tags:
            if not isinstance(tag, dict):
                continue
                
            # Handle different formats
            key = tag.get('Key', tag.get('key', ''))
            value = tag.get('Value', tag.get('value', ''))
            
            # Validate according to AWS tag rules
            if not key or len(key) > 128:
                continue
            if len(value) > 256:
                value = value[:256]
                
            # Add to result
            result.append({'Key': key, 'Value': value})
            
        return result
    
    @api.model
    def pretty_print_aws_error(self, error):
        """
        Format an AWS error into a user-friendly message.
        
        Args:
            error: Exception object
            
        Returns:
            User-friendly error message
        """
        if isinstance(error, botocore.exceptions.ClientError):
            # Extract error code and message
            error_code = error.response.get('Error', {}).get('Code', 'Unknown')
            error_message = error.response.get('Error', {}).get('Message', str(error))
            
            # Map common error codes to user-friendly messages
            error_mappings = {
                'AccessDenied': _("Access denied. Check IAM permissions."),
                'InvalidAccessKeyId': _("Invalid AWS access key ID."),
                'SignatureDoesNotMatch': _("Invalid AWS secret access key."),
                'AuthFailure': _("Authentication failed. Check your AWS credentials."),
                'ResourceNotFoundException': _("The specified resource was not found."),
                'ValidationError': _("Validation error: %s") % error_message,
                'InvalidParameterValue': _("Invalid parameter value: %s") % error_message,
                'MissingParameter': _("Missing required parameter: %s") % error_message,
                'OptInRequired': _("Your AWS account is not subscribed to this service in this region."),
                'RequestExpired': _("Request expired. Check your system clock."),
                'ThrottlingException': _("Request throttled. Try again later."),
                'ServiceUnavailable': _("AWS service is currently unavailable. Try again later."),
            }
            
            return error_mappings.get(error_code, f"{error_code}: {error_message}")
            
        elif isinstance(error, botocore.exceptions.EndpointConnectionError):
            return _("Cannot connect to AWS. Check your network connection or VPN settings.")
            
        elif isinstance(error, botocore.exceptions.NoCredentialsError):
            return _("No AWS credentials found. Please configure AWS credentials.")
            
        else:
            return str(error)