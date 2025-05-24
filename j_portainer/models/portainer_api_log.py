#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
import json
import logging
from datetime import datetime


class PortainerApiLog(models.Model):
    _name = 'j_portainer.api_log'
    _description = 'Portainer API Request Log'
    _order = 'create_date desc'
    _rec_name = 'endpoint'

    server_id = fields.Many2one('j_portainer.server', string='Portainer Server', required=True, 
                               ondelete='cascade', index=True)
    environment_id = fields.Integer('Environment ID', help="Portainer environment ID if applicable")
    environment_name = fields.Char('Environment Name', help="Portainer environment name if applicable")
    
    endpoint = fields.Char('API Endpoint', required=True, help="The API endpoint that was called")
    method = fields.Selection([
        ('GET', 'GET'),
        ('POST', 'POST'),
        ('PUT', 'PUT'), 
        ('DELETE', 'DELETE')
    ], string='HTTP Method', required=True)
    
    request_date = fields.Datetime('Request Date', required=True, default=fields.Datetime.now)
    response_time_ms = fields.Integer('Response Time (ms)', help="Response time in milliseconds")
    
    status_code = fields.Integer('Status Code', help="HTTP status code of the response")
    status = fields.Selection([
        ('success', 'Success'),
        ('error', 'Error'),
        ('warning', 'Warning'),
    ], string='Status', compute='_compute_status', store=True)
    
    error_message = fields.Text('Error Message', help="Error message if request failed")
    request_data = fields.Text('Request Data', help="Data sent with the request")
    response_data = fields.Text('Response Data', help="Data received in the response")
    
    # Operation type field has been removed as requested
    
    @api.depends('status_code')
    def _compute_status(self):
        """Compute the status based on the HTTP status code"""
        for log in self:
            if not log.status_code:
                log.status = 'error'
            elif 200 <= log.status_code < 300:
                log.status = 'success'
            elif 300 <= log.status_code < 400:
                log.status = 'warning'
            else:
                log.status = 'error'
    
    def name_get(self):
        """Custom name get to show more descriptive names in the UI"""
        result = []
        for log in self:
            name = f"{log.method} {log.endpoint}"
            if log.status:
                name = f"{name} ({log.status})"
            result.append((log.id, name))
        return result
        
    @api.model
    def purge_old_logs(self, days=None):
        """Delete API logs older than the specified number of days
        
        This method is meant to be called by a scheduled action to regularly
        delete old API logs and prevent database bloat.
        
        Args:
            days (int, optional): Number of days to keep logs for. If not provided,
                                 the value will be read from system parameters.
                                 Logs older than this will be deleted.
        
        Returns:
            int: Number of logs deleted
        """
        # If days parameter is not provided, read from system parameter
        if days is None:
            param_days = self.env['ir.config_parameter'].sudo().get_param('j_portainer.api_log_delete_days', '1')
            try:
                days = int(param_days)
            except (ValueError, TypeError):
                days = 1
        
        # Ensure days is a valid positive integer
        if not isinstance(days, int) or days < 1:
            days = 1
            
        # Calculate cutoff date (current date minus specified days)
        import datetime
        from datetime import timedelta
        
        # Get current date without time component
        today = fields.Date.today()
        cutoff_date = today - timedelta(days=days)
        
        # Find logs older than the cutoff date (comparing only the date part)
        old_logs = self.search([
            ('request_date', '<=', cutoff_date)
        ])
        
        # Count records for return value
        count = len(old_logs)
        
        # Delete the old logs
        if old_logs:
            old_logs.unlink()
            
        # Log the purge operation
        _logger = logging.getLogger(__name__)
        _logger.info(f"Purged {count} API logs older than {days} days")
            
        return count