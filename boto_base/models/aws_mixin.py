# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
#
# Copyright (C) 2023 JAAH

import logging
import boto3
import botocore
from odoo import api, fields, models, _, tools
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class AWSClientMixin(models.AbstractModel):
    """
    Mixin to provide AWS client functionality to any model.
    This allows easy access to AWS services with proper error handling.
    """
    _name = 'aws.client.mixin'
    _description = 'AWS Client Mixin'
    
    def get_aws_credentials(self, aws_credentials_id=None, service_name=None, region_name=None):
        """
        Get AWS credentials record to use for API calls.
        
        Args:
            aws_credentials_id: Optional specific credentials ID to use
            service_name: AWS service name to get credentials for
            region_name: AWS region to get credentials for
            
        Returns:
            aws.credentials record
        """
        # Try to get credentials in this order:
        # 1. Explicitly provided credentials ID
        # 2. Credentials appropriate for the specified service/region
        # 3. Default credentials
        # 4. Any valid credentials
        
        AWSCredentials = self.env['aws.credentials']
        
        if aws_credentials_id:
            credentials = AWSCredentials.browse(aws_credentials_id)
            if not credentials.exists() or not credentials.active:
                raise UserError(_('The specified AWS credentials do not exist or are inactive.'))
            return credentials
            
        if service_name:
            credentials = AWSCredentials.get_credentials_for_service(service_name, region_name)
            if credentials:
                return credentials
            
        # Get default credentials
        credentials = AWSCredentials.get_default_credentials()
        if credentials:
            return credentials
            
        # Get any valid credentials
        credentials = AWSCredentials.search([
            ('active', '=', True),
            ('is_valid', '=', True)
        ], limit=1)
        
        if not credentials:
            raise UserError(_('No valid AWS credentials found. Please configure credentials in AWS Settings.'))
            
        return credentials
    
    def get_aws_client(self, service_name, aws_credentials_id=None, region_name=None, endpoint_url=None):
        """
        Get an AWS service client with proper error handling.
        
        Args:
            service_name: AWS service name (e.g., 's3', 'ec2')
            aws_credentials_id: Optional specific credentials ID to use
            region_name: Optional region name to override default
            endpoint_url: Optional endpoint URL to override default
            
        Returns:
            boto3 client object
        """
        credentials = self.get_aws_credentials(
            aws_credentials_id=aws_credentials_id,
            service_name=service_name,
            region_name=region_name
        )
        
        return credentials.get_client(
            service_name=service_name,
            region_name=region_name,
            endpoint_url=endpoint_url
        )
    
    def get_aws_resource(self, service_name, aws_credentials_id=None, region_name=None, endpoint_url=None):
        """
        Get an AWS service resource with proper error handling.
        
        Args:
            service_name: AWS service name (e.g., 's3', 'ec2')
            aws_credentials_id: Optional specific credentials ID to use
            region_name: Optional region name to override default
            endpoint_url: Optional endpoint URL to override default
            
        Returns:
            boto3 resource object
        """
        credentials = self.get_aws_credentials(
            aws_credentials_id=aws_credentials_id,
            service_name=service_name,
            region_name=region_name
        )
        
        return credentials.get_resource(
            service_name=service_name,
            region_name=region_name,
            endpoint_url=endpoint_url
        )
    
    def aws_operation(self, service_name, operation, aws_credentials_id=None, region_name=None, **kwargs):
        """
        Execute an AWS operation with error handling.
        
        Args:
            service_name: AWS service name
            operation: The operation name to execute
            aws_credentials_id: Optional credentials ID
            region_name: Optional region name
            **kwargs: Arguments to pass to the operation
            
        Returns:
            Operation result
        """
        client = self.get_aws_client(
            service_name=service_name,
            aws_credentials_id=aws_credentials_id,
            region_name=region_name
        )
        
        credentials = self.get_aws_credentials(
            aws_credentials_id=aws_credentials_id,
            service_name=service_name,
            region_name=region_name
        )
        
        method = getattr(client, operation, None)
        if not method:
            raise UserError(_("Operation '%s' not found for AWS service '%s'") % (operation, service_name))
            
        return credentials.execute_with_error_handling(method, **kwargs)
    
    def log_aws_operation(self, service_name, operation, success, result=None, error=None):
        """
        Log an AWS operation for auditing purposes.
        Subclasses can override to store logs in a model.
        
        Args:
            service_name: AWS service name
            operation: Operation name
            success: Whether the operation succeeded
            result: Operation result (if success)
            error: Error message (if not success)
        """
        if success:
            _logger.info(
                "AWS %s - %s: Success", 
                service_name, 
                operation
            )
        else:
            _logger.error(
                "AWS %s - %s: Error: %s", 
                service_name, 
                operation, 
                error
            )


class AWSServiceImplementationMixin(models.AbstractModel):
    """
    Mixin to be used by models implementing specific AWS services.
    Provides common fields and methods for AWS service configuration.
    """
    _name = 'aws.service.implementation.mixin'
    _description = 'AWS Service Implementation Mixin'
    _inherit = ['aws.client.mixin']
    
    aws_credentials_id = fields.Many2one(
        'aws.credentials', 
        string='AWS Credentials',
        domain=[('active', '=', True), ('is_valid', '=', True)]
    )
    aws_region = fields.Char(
        string='AWS Region',
        default=lambda self: self.env['ir.config_parameter'].sudo().get_param('boto_base.aws_default_region', 'us-east-1')
    )
    aws_endpoint_url = fields.Char(
        string='Custom Endpoint URL',
        help='Optional custom endpoint URL for this AWS service'
    )
    last_sync = fields.Datetime(string='Last Synchronization')
    
    def get_service_client(self, service_name):
        """Get a service client using this record's credentials and region"""
        self.ensure_one()
        return self.get_aws_client(
            service_name=service_name,
            aws_credentials_id=self.aws_credentials_id.id if self.aws_credentials_id else None,
            region_name=self.aws_region,
            endpoint_url=self.aws_endpoint_url
        )
        
    def get_service_resource(self, service_name):
        """Get a service resource using this record's credentials and region"""
        self.ensure_one()
        return self.get_aws_resource(
            service_name=service_name,
            aws_credentials_id=self.aws_credentials_id.id if self.aws_credentials_id else None,
            region_name=self.aws_region,
            endpoint_url=self.aws_endpoint_url
        )
        
    def execute_service_operation(self, service_name, operation, **kwargs):
        """Execute a service operation using this record's credentials and region"""
        self.ensure_one()
        return self.aws_operation(
            service_name=service_name,
            operation=operation,
            aws_credentials_id=self.aws_credentials_id.id if self.aws_credentials_id else None,
            region_name=self.aws_region,
            **kwargs
        )