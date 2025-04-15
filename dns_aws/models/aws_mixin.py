# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
#
# Copyright (C) 2023 JAAH

import logging
import time
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import boto3
import botocore.exceptions

_logger = logging.getLogger(__name__)

class AWSClientMixin(models.AbstractModel):
    _name = 'dns.aws.client.mixin'
    _description = 'AWS Client Mixin'
    _inherit = ['dns.aws.log.mixin']

    aws_credentials_id = fields.Many2one('dns.aws.credentials', string='AWS Credentials')
    aws_region = fields.Char(string='AWS Region', default='us-east-1')
    
    def _get_aws_credentials(self):
        """
        Get AWS credentials for this record
        Checks for AWS credentials on the record first, falls back to default if needed
        """
        self.ensure_one()
        
        # If we have AWS credentials directly on the record, use those
        if hasattr(self, 'aws_credentials_id') and self.aws_credentials_id:
            return {
                'aws_access_key_id': self.aws_credentials_id.aws_access_key_id,
                'aws_secret_access_key': self.aws_credentials_id.aws_secret_access_key,
            }
            
        # Otherwise, look for the field in related models
        if hasattr(self, 'route53_config_id') and self.route53_config_id and hasattr(self.route53_config_id, 'aws_credentials_id'):
            return {
                'aws_access_key_id': self.route53_config_id.aws_credentials_id.aws_access_key_id,
                'aws_secret_access_key': self.route53_config_id.aws_credentials_id.aws_secret_access_key,
            }
            
        # Default fallback - get credentials from system parameters
        # This should be avoided in production environments for security reasons
        IrParam = self.env['ir.config_parameter'].sudo()
        return {
            'aws_access_key_id': IrParam.get_param('dns_aws.default_aws_access_key_id', ''),
            'aws_secret_access_key': IrParam.get_param('dns_aws.default_aws_secret_access_key', ''),
        }
        
    def _get_aws_region(self):
        """
        Get AWS region for this record
        Checks for AWS region on the record first, falls back to default if needed
        """
        self.ensure_one()
        
        # If we have region directly on the record, use it
        if hasattr(self, 'aws_region') and self.aws_region:
            return self.aws_region
            
        # Otherwise, look for the field in related models
        if hasattr(self, 'route53_config_id') and self.route53_config_id and hasattr(self.route53_config_id, 'aws_region'):
            return self.route53_config_id.aws_region
            
        # Fallback to default region
        return self._get_default_region()
        
    @api.model
    def _get_default_region(self):
        """Get default AWS region from system parameters"""
        return self.env['ir.config_parameter'].sudo().get_param('dns_aws.default_aws_region', 'us-east-1')
        
    def _get_boto3_client(self, service_name, region_name=None, credentials=None):
        """
        Create and return a boto3 client for the specified AWS service
        
        Args:
            service_name: AWS service name (e.g., 'route53', 'ec2')
            region_name: AWS region name (default: None, which uses the record's region)
            credentials: AWS credentials dict (default: None, which uses the record's credentials)
            
        Returns:
            A boto3 client for the specified service
        """
        self.ensure_one()
        
        # Use provided credentials or get them from the record
        creds = credentials or self._get_aws_credentials()
        
        # Use provided region or get it from the record
        region = region_name or self._get_aws_region()
        
        # Validate credentials
        if not creds.get('aws_access_key_id') or not creds.get('aws_secret_access_key'):
            raise ValidationError(_("AWS credentials are not properly configured."))
            
        try:
            return boto3.client(
                service_name,
                aws_access_key_id=creds['aws_access_key_id'],
                aws_secret_access_key=creds['aws_secret_access_key'],
                region_name=region
            )
        except Exception as e:
            _logger.error("Failed to create boto3 client for service '%s': %s", service_name, str(e))
            raise ValidationError(_("Failed to create AWS client: %s") % str(e))
            
    def execute_aws_operation(self, service_name, operation_name, **kwargs):
        """
        Execute an AWS operation with logging and error handling
        
        Args:
            service_name: AWS service name (e.g., 'route53', 'ec2')
            operation_name: Name of the operation to execute
            **kwargs: Arguments to pass to the operation
            
        Returns:
            The operation response
        """
        self.ensure_one()
        
        # Create the client
        client = self._get_boto3_client(service_name)
        
        # Get the operation from the client
        if not hasattr(client, operation_name):
            raise ValidationError(_("Operation '%s' not found for service '%s'") % (operation_name, service_name))
        operation = getattr(client, operation_name)
        
        # Prepare logging data
        log_name = f"{service_name}.{operation_name}"
        
        # Convert args to a dictionary for logging
        request_data = kwargs
        
        # Execute the operation with timing
        start_time = time.time()
        try:
            response = operation(**kwargs)
            duration = time.time() - start_time
            
            # Log successful operation
            self._log_aws_operation(
                name=log_name,
                aws_service=service_name,
                status='success',
                request_data=request_data,
                response_data=response,
                duration=duration
            )
            
            return response
        except botocore.exceptions.ClientError as e:
            duration = time.time() - start_time
            error_response = e.response if hasattr(e, 'response') else {}
            error_message = str(e)
            
            # Log failed operation
            self._log_aws_operation(
                name=log_name,
                aws_service=service_name,
                status='error',
                request_data=request_data,
                response_data=error_response,
                duration=duration,
                error_message=error_message
            )
            
            # Re-raise as Odoo ValidationError
            error_code = error_response.get('Error', {}).get('Code', 'Unknown')
            raise ValidationError(_("AWS operation failed: %s - %s") % (error_code, error_message))