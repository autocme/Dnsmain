#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
import json
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
    
    operation_type = fields.Selection([
        ('sync_environment', 'Sync Environments'),
        ('sync_container', 'Sync Containers'),
        ('sync_image', 'Sync Images'),
        ('sync_volume', 'Sync Volumes'),
        ('sync_network', 'Sync Networks'),
        ('sync_template', 'Sync Templates'),
        ('sync_custom_template', 'Sync Custom Templates'),
        ('sync_stack', 'Sync Stacks'),
        ('create_template', 'Create Template'),
        ('update_template', 'Update Template'),
        ('delete_template', 'Delete Template'),
        ('deploy_template', 'Deploy Template'),
        ('test_connection', 'Test Connection'),
        ('other', 'Other Operation')
    ], string='Operation Type', default='other')
    
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