# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
#
# Copyright (C) 2023 JAAH

import logging
import json
from datetime import datetime
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)

class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder that can handle datetime objects"""
    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat()
        return super(DateTimeEncoder, self).default(o)

class AWSOperationLog(models.Model):
    _name = 'dns.aws.operation.log'
    _description = 'AWS Operation Log'
    _order = 'create_date desc'

    name = fields.Char(string='Operation', required=True)
    aws_service = fields.Char(string='AWS Service', required=True)
    status = fields.Selection([
        ('success', 'Success'),
        ('error', 'Error'),
        ('warning', 'Warning'),
    ], string='Status', required=True, default='success')
    model = fields.Char(string='Model', help='The Odoo model that initiated the operation')
    res_id = fields.Integer(string='Record ID', help='The ID of the record that initiated the operation')
    resource_id = fields.Char(string='AWS Resource ID', help='The AWS resource identifier involved in the operation')
    request_data = fields.Text(string='Request Data', help='The data sent to AWS')
    response_data = fields.Text(string='Response Data', help='The response received from AWS')
    duration = fields.Float(string='Duration (s)', help='Operation duration in seconds')
    user_id = fields.Many2one('res.users', string='User', default=lambda self: self.env.user.id)
    error_message = fields.Text(string='Error Message')
    
    @api.model
    def log_operation(self, name, aws_service, status='success', model=None, res_id=None, 
                     resource_id=None, request_data=None, response_data=None, duration=0.0, error_message=None):
        """
        Log an AWS operation
        
        Args:
            name: Name of the operation
            aws_service: The AWS service used (e.g., 'route53', 'ec2')
            status: Operation status ('success', 'error', 'warning')
            model: The Odoo model that initiated the operation
            res_id: The ID of the record that initiated the operation
            resource_id: The AWS resource identifier involved in the operation
            request_data: The data sent to AWS (dict or str)
            response_data: The response received from AWS (dict or str)
            duration: Operation duration in seconds
            error_message: Error message if status is 'error'
        
        Returns:
            The created log record
        """
        # Convert dict to JSON string for storage with custom encoding for datetime objects
        if request_data and isinstance(request_data, dict):
            request_data = json.dumps(request_data, indent=2, cls=DateTimeEncoder)
        if response_data and isinstance(response_data, dict):
            response_data = json.dumps(response_data, indent=2, cls=DateTimeEncoder)
            
        vals = {
            'name': name,
            'aws_service': aws_service,
            'status': status,
            'model': model,
            'res_id': res_id,
            'resource_id': resource_id,
            'request_data': request_data,
            'response_data': response_data,
            'duration': duration,
            'error_message': error_message,
        }
        
        try:
            return self.create(vals)
        except Exception as e:
            # Fail gracefully - logging should never cause operations to fail
            _logger.error("Failed to create AWS operation log: %s", str(e))
            return self.env['dns.aws.operation.log']  # Return empty recordset


class AWSLogMixin(models.AbstractModel):
    _name = 'dns.aws.log.mixin'
    _description = 'AWS Log Mixin'
    
    def _log_aws_operation(self, name, aws_service, status='success', resource_id=None,
                          request_data=None, response_data=None, duration=0.0, error_message=None):
        """
        Log an AWS operation from a model
        
        This is a convenience method that automatically captures the model and res_id
        """
        return self.env['dns.aws.operation.log'].log_operation(
            name=name,
            aws_service=aws_service,
            status=status,
            model=self._name,
            res_id=self.id if hasattr(self, 'id') else None,
            resource_id=resource_id,
            request_data=request_data,
            response_data=response_data,
            duration=duration,
            error_message=error_message,
        )