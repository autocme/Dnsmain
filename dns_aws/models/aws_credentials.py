# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
#
# Copyright (C) 2023 JAAH

import logging
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import boto3

_logger = logging.getLogger(__name__)

class AWSCredentials(models.Model):
    _name = 'dns.aws.credentials'
    _description = 'AWS Credentials'
    
    name = fields.Char(string='Credentials Name', required=True)
    aws_access_key_id = fields.Char(string='AWS Access Key ID', required=True)
    aws_secret_access_key = fields.Char(string='AWS Secret Access Key', required=True)
    active = fields.Boolean(default=True)
    
    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'Credentials name must be unique!')
    ]
    
    def test_credentials(self):
        """Test the AWS credentials by trying to create a client"""
        try:
            # Create a simple client to test the credentials
            # Using IAM service as it's less likely to have permission issues
            client = boto3.client(
                'iam',
                aws_access_key_id=self.aws_access_key_id,
                aws_secret_access_key=self.aws_secret_access_key,
                region_name='us-east-1'  # Default region for testing
            )
            
            # Try to get current user to validate credentials
            response = client.get_user()
            
            # If we get here, credentials are valid
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Credentials Test Successful'),
                    'message': _('Successfully authenticated with AWS.'),
                    'sticky': False,
                    'type': 'success',
                }
            }
        except Exception as e:
            _logger.error("AWS credentials test failed: %s", str(e))
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Credentials Test Failed'),
                    'message': str(e),
                    'sticky': False,
                    'type': 'danger',
                }
            }