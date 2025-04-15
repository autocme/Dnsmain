# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
#
# Copyright (C) 2023 JAAH

import json
import logging
from datetime import datetime
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)

class AWSOperationLog(models.Model):
    """
    Model to store logs of AWS API operations for auditing and debugging.
    This helps track AWS operations across the system.
    """
    _name = 'aws.operation.log'
    _description = 'AWS Operation Log'
    _order = 'create_date desc'
    
    name = fields.Char(string='Operation', required=True, index=True)
    service_name = fields.Char(string='AWS Service', required=True, index=True)
    credentials_id = fields.Many2one('aws.credentials', string='AWS Credentials')
    region = fields.Char(string='AWS Region')
    
    status = fields.Selection([
        ('success', 'Success'),
        ('error', 'Error'),
        ('warning', 'Warning'),
    ], string='Status', required=True, default='success', index=True)
    
    duration_ms = fields.Integer(string='Duration (ms)', help='Operation duration in milliseconds')
    request_data = fields.Text(string='Request Data', help='JSON data sent in the request')
    response_data = fields.Text(string='Response Data', help='JSON data received in the response')
    error_message = fields.Text(string='Error Message')
    
    user_id = fields.Many2one('res.users', string='User', default=lambda self: self.env.user.id)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company.id)
    
    model = fields.Char(string='Related Model', index=True, help='Odoo model that triggered the operation')
    res_id = fields.Integer(string='Record ID', index=True, help='ID of the record that triggered the operation')
    record_name = fields.Char(string='Record Name', compute='_compute_record_name', store=True)
    
    @api.depends('model', 'res_id')
    def _compute_record_name(self):
        """Compute the name of the related record, if any"""
        for log in self:
            if log.model and log.res_id:
                try:
                    record = self.env[log.model].browse(log.res_id).exists()
                    if record:
                        log.record_name = record.display_name
                    else:
                        log.record_name = f"{log.model},{log.res_id} (deleted)"
                except Exception:
                    log.record_name = f"{log.model},{log.res_id}"
            else:
                log.record_name = False
    
    @api.model
    def log_operation(self, service_name, operation_name, status, 
                     credentials=None, region=None, model=None, res_id=None,
                     request_data=None, response_data=None, error_message=None, 
                     duration_ms=None):
        """
        Log an AWS operation for auditing.
        
        Args:
            service_name: AWS service name (e.g., 's3', 'ec2')
            operation_name: Name of the operation performed
            status: 'success', 'error', or 'warning'
            credentials: Optional aws.credentials record
            region: Optional AWS region used
            model: Optional Odoo model name that triggered the operation
            res_id: Optional ID of the record that triggered the operation
            request_data: Optional data sent in the request
            response_data: Optional data received in the response
            error_message: Optional error message if status is 'error'
            duration_ms: Optional duration of the operation in milliseconds
        """
        # Convert request/response data to JSON strings if they're not already
        if request_data and not isinstance(request_data, str):
            try:
                request_data = json.dumps(request_data, indent=2)
            except Exception:
                request_data = str(request_data)
                
        if response_data and not isinstance(response_data, str):
            try:
                response_data = json.dumps(response_data, indent=2)
            except Exception:
                response_data = str(response_data)
                
        # Create log entry
        vals = {
            'name': operation_name,
            'service_name': service_name,
            'status': status,
            'region': region,
            'credentials_id': credentials.id if credentials else False,
            'model': model,
            'res_id': res_id,
            'request_data': request_data,
            'response_data': response_data,
            'error_message': error_message,
            'duration_ms': duration_ms,
        }
        
        # Create the log entry
        try:
            return self.create(vals)
        except Exception as e:
            _logger.error("Failed to create AWS operation log: %s", e)
            return False


class AWSServiceLogger(models.AbstractModel):
    """
    Mixin to add AWS operation logging functionality.
    This extends the aws.client.mixin with better logging capabilities.
    """
    _name = 'aws.service.logger'
    _description = 'AWS Service Logger'
    _inherit = ['aws.client.mixin']
    
    def aws_operation_with_logging(self, service_name, operation, with_result=False, 
                                  log_request=True, log_response=True, **kwargs):
        """
        Execute an AWS operation with comprehensive logging.
        
        Args:
            service_name: AWS service name (e.g., 's3', 'ec2')
            operation: Name of the operation to perform
            with_result: Whether to include the operation result in the return value
            log_request: Whether to log the request data
            log_response: Whether to log the response data
            **kwargs: Arguments to pass to the operation
            
        Returns:
            If with_result is True: (success, result_or_error)
            If with_result is False: success (boolean)
        """
        start_time = datetime.now()
        model = self._name
        res_id = self.id if isinstance(self.id, int) else False
        
        # Extract credentials information
        aws_credentials_id = kwargs.pop('aws_credentials_id', None)
        region_name = kwargs.pop('region_name', None)
        
        # Get credentials
        try:
            credentials = self.get_aws_credentials(
                aws_credentials_id=aws_credentials_id,
                service_name=service_name,
                region_name=region_name
            )
        except Exception as e:
            # Log error getting credentials
            duration = (datetime.now() - start_time).total_seconds() * 1000
            self.env['aws.operation.log'].log_operation(
                service_name=service_name,
                operation_name=operation,
                status='error',
                region=region_name,
                model=model,
                res_id=res_id,
                error_message=f"Failed to get AWS credentials: {str(e)}",
                duration_ms=int(duration)
            )
            if with_result:
                return False, str(e)
            return False
            
        # Prepare request data for logging
        request_data = kwargs if log_request else None
        
        try:
            # Get the client
            client = self.get_aws_client(
                service_name=service_name,
                aws_credentials_id=credentials.id,
                region_name=region_name
            )
            
            # Get the operation method
            method = getattr(client, operation, None)
            if not method:
                raise ValueError(f"Operation '{operation}' not found for AWS service '{service_name}'")
                
            # Execute the operation
            result = method(**kwargs)
            
            # Calculate duration
            duration = (datetime.now() - start_time).total_seconds() * 1000
            
            # Log success
            self.env['aws.operation.log'].log_operation(
                service_name=service_name,
                operation_name=operation,
                status='success',
                credentials=credentials,
                region=region_name or credentials.aws_default_region,
                model=model,
                res_id=res_id,
                request_data=request_data,
                response_data=result if log_response else None,
                duration_ms=int(duration)
            )
            
            if with_result:
                return True, result
            return True
            
        except Exception as e:
            # Calculate duration
            duration = (datetime.now() - start_time).total_seconds() * 1000
            
            # Log error
            self.env['aws.operation.log'].log_operation(
                service_name=service_name,
                operation_name=operation,
                status='error',
                credentials=credentials,
                region=region_name or credentials.aws_default_region,
                model=model,
                res_id=res_id,
                request_data=request_data,
                error_message=str(e),
                duration_ms=int(duration)
            )
            
            if with_result:
                return False, str(e)
            return False