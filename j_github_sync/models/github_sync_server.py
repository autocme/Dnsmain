#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import json
import logging
from datetime import datetime, timedelta
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class GitHubSyncServer(models.Model):
    """
    GitHub Sync Server Configuration Model
    
    This model manages GitHub Sync Server connections and configurations.
    It handles API authentication, server settings, and provides methods
    for interacting with the GitHub Sync Server API.
    """
    
    _name = 'github.sync.server'
    _description = 'GitHub Sync Server Configuration'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'gss_name'
    _rec_name = 'gss_name'

    # ========================================================================
    # BASIC FIELDS
    # ========================================================================
    
    gss_name = fields.Char(
        string='Server Name',
        required=True,
        tracking=True,
        help='Descriptive name for this GitHub Sync Server instance'
    )
    
    gss_server_url = fields.Char(
        string='Server URL',
        required=True,
        tracking=True,
        help='Base URL of the GitHub Sync Server (e.g., http://3.110.88.87:5000)',
        default='http://3.110.88.87:5000'
    )
    
    gss_api_key = fields.Char(
        string='API Key',
        required=True,
        tracking=True,
        help='Bearer token for API authentication'
    )
    
    # ========================================================================
    # STATUS AND MONITORING
    # ========================================================================
    
    gss_active = fields.Boolean(
        string='Active',
        default=True,
        tracking=True,
        help='Whether this server configuration is active'
    )
    
    gss_last_sync = fields.Datetime(
        string='Last Sync',
        readonly=True,
        tracking=True,
        help='Timestamp of the last successful synchronization'
    )
    
    gss_server_status = fields.Selection([
        ('online', 'Online'),
        ('offline', 'Offline'),
        ('error', 'Error'),
        ('unknown', 'Unknown')
    ], string='Server Status', default='unknown', readonly=True, tracking=True)
    
    # ========================================================================
    # STATISTICS
    # ========================================================================
    
    gss_repository_count = fields.Integer(
        string='Repositories',
        compute='_compute_repository_count',
        help='Number of repositories managed by this server'
    )
    
    gss_log_count = fields.Integer(
        string='Logs',
        compute='_compute_log_count',
        help='Number of logs for this server'
    )
    
    # ========================================================================
    # RELATIONSHIPS
    # ========================================================================
    
    gss_repository_ids = fields.One2many(
        'github.repository',
        'gr_server_id',
        string='Repositories',
        help='Repositories managed by this server'
    )
    
    gss_log_ids = fields.One2many(
        'github.sync.log',
        'gsl_server_id',
        string='Logs',
        help='Logs from this server'
    )
    
    gss_company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        tracking=True
    )
    
    gss_demo_mode = fields.Boolean(
        string='Demo Mode',
        default=False,
        tracking=True,
        help='Enable demo mode to test functionality without external server'
    )
    
    gss_last_request_details = fields.Text(
        string='Last Request Details',
        readonly=True,
        help='Details of the last API request and response'
    )

    # ========================================================================
    # COMPUTED FIELDS
    # ========================================================================
    
    @api.depends('gss_repository_ids')
    def _compute_repository_count(self):
        """Compute the number of repositories."""
        for record in self:
            record.gss_repository_count = len(record.gss_repository_ids)
    
    @api.depends('gss_log_ids')
    def _compute_log_count(self):
        """Compute the number of logs."""
        for record in self:
            record.gss_log_count = len(record.gss_log_ids)

    # ========================================================================
    # CONSTRAINTS
    # ========================================================================
    
    _sql_constraints = [
        ('unique_gss_name', 'UNIQUE(gss_name, gss_company_id)', 'Server name must be unique per company.'),
    ]

    @api.constrains('gss_server_url')
    def _check_server_url(self):
        """Validate server URL format."""
        for record in self:
            if record.gss_server_url and not record.gss_server_url.startswith(('http://', 'https://')):
                raise ValidationError(_('Server URL must start with http:// or https://'))

    # ========================================================================
    # API METHODS
    # ========================================================================
    
    def _get_headers(self):
        """Get API headers with authentication."""
        self.ensure_one()
        return {
            'Authorization': f'Bearer {self.gss_api_key}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
    
    def _get_api_url(self, endpoint):
        """Get full API URL for endpoint."""
        self.ensure_one()
        base_url = self.gss_server_url.rstrip('/')
        endpoint = endpoint.lstrip('/')
        return f"{base_url}/api/{endpoint}"
    
    def _make_request(self, method, endpoint, data=None, params=None):
        """Make HTTP request to the API."""
        self.ensure_one()
        
        # Demo mode simulation
        if self.gss_demo_mode:
            result = self._simulate_api_response(method, endpoint)
            self._log_request_details(method, endpoint, data, result, demo_mode=True)
            return result
        
        url = self._get_api_url(endpoint)
        headers = self._get_headers()
        
        try:
            _logger.info(f"Making {method} request to {url}")
            
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=data,
                params=params,
                timeout=10,
                verify=False
            )
            
            if response.status_code == 200:
                result = response.json()
                self._log_request_details(method, endpoint, data, result, response_code=response.status_code)
                return result
            elif response.status_code in [401, 403]:
                self._log_request_details(method, endpoint, data, None, response_code=response.status_code, error='Authentication failed')
                raise UserError(_('Authentication failed. Please check your API key.'))
            elif response.status_code == 404:
                self._log_request_details(method, endpoint, data, None, response_code=response.status_code, error='Endpoint not found')
                raise UserError(_('Endpoint not found: %s') % endpoint)
            else:
                response.raise_for_status()
                
        except requests.exceptions.ConnectTimeout as e:
            self._log_request_details(method, endpoint, data, None, error=str(e))
            raise UserError(_('Connection timeout. The server at %s is not responding within 10 seconds. Try enabling Demo Mode for testing.') % self.gss_server_url)
        except requests.exceptions.ConnectionError as e:
            self._log_request_details(method, endpoint, data, None, error=str(e))
            if 'Name or service not known' in str(e):
                raise UserError(_('Cannot resolve hostname. Please check the server URL: %s. Try enabling Demo Mode for testing.') % self.gss_server_url)
            elif 'Connection refused' in str(e):
                raise UserError(_('Connection refused. The server might be offline: %s. Try enabling Demo Mode for testing.') % self.gss_server_url)
            else:
                raise UserError(_('Connection failed: %s. Try enabling Demo Mode for testing.') % str(e))
        except requests.exceptions.Timeout as e:
            self._log_request_details(method, endpoint, data, None, error=str(e))
            raise UserError(_('Request timeout. Try enabling Demo Mode for testing.'))
        except requests.exceptions.RequestException as e:
            self._log_request_details(method, endpoint, data, None, error=str(e))
            raise UserError(_('Request failed: %s. Try enabling Demo Mode for testing.') % str(e))
        
        return None
    
    def _log_request_details(self, method, endpoint, request_data, response_data, response_code=None, error=None, demo_mode=False):
        """Log request and response details."""
        if response_data:
            # Store the raw response as-is
            self.write({'gss_last_request_details': json.dumps(response_data, indent=2)})
        elif error:
            # Store error information
            error_details = {
                'error': error,
                'endpoint': endpoint,
                'method': method
            }
            self.write({'gss_last_request_details': json.dumps(error_details, indent=2)})
    
    def _simulate_api_response(self, method, endpoint):
        """Simulate API responses for demo mode."""
        import time
        time.sleep(0.5)  # Simulate network delay
        
        if endpoint == 'status':
            return {
                'success': True,
                'data': {
                    'status': 'online',
                    'version': '1.0.0',
                    'uptime': '2 days'
                },
                'message': 'Server is running'
            }
        elif endpoint == 'repositories':
            return {
                'success': True,
                'data': [
                    {
                        'id': 'demo_repo_1',
                        'name': 'Dnsmain',
                        'url': 'git@github.com:autocme/Dnsmain.git',
                        'branch': 'main',
                        'local_path': '/repos/Dnsmain',
                        'status': 'success',
                        'last_pull': '2025-06-22 07:50',
                        'description': 'DNS management system',
                        'private': False
                    },
                    {
                        'id': 'demo_repo_2', 
                        'name': 'server-backend',
                        'url': 'https://github.com/OCA/server-backend.git',
                        'branch': '17.0',
                        'local_path': '/repos/server-backend',
                        'status': 'success',
                        'last_pull': '2025-06-22 00:07',
                        'description': 'OCA server backend modules',
                        'private': False
                    }
                ],
                'message': 'Repositories retrieved successfully'
            }
        elif endpoint == 'logs':
            from datetime import timedelta
            return {
                'success': True,
                'data': [
                    {
                        'id': 'log_1',
                        'timestamp': fields.Datetime.now().isoformat(),
                        'operation': 'webhook',
                        'status': 'success',
                        'message': 'Successfully processed webhook for Dnsmain Repository: Dnsmain'
                    },
                    {
                        'id': 'log_2',
                        'timestamp': (fields.Datetime.now() - timedelta(minutes=5)).isoformat(),
                        'operation': 'pull',
                        'status': 'success',
                        'message': 'Repository pulled successfully from main branch'
                    },
                    {
                        'id': 'log_3',
                        'timestamp': (fields.Datetime.now() - timedelta(minutes=10)).isoformat(),
                        'operation': 'clone',
                        'status': 'error',
                        'message': 'Failed to clone repository: authentication failed'
                    },
                    {
                        'id': 'log_4',
                        'timestamp': (fields.Datetime.now() - timedelta(minutes=15)).isoformat(),
                        'operation': 'restart',
                        'status': 'warning',
                        'message': 'Container restart requested due to configuration changes'
                    }
                ],
                'message': 'Logs retrieved successfully'
            }
        elif endpoint.startswith('repositories/') and endpoint.endswith('/sync'):
            return {
                'success': True,
                'data': {},
                'message': 'Repository sync initiated successfully'
            }
        else:
            return {
                'success': False,
                'message': f'Demo endpoint not implemented: {endpoint}'
            }
    
    def test_connection(self):
        """Test connection to the GitHub Sync Server."""
        self.ensure_one()
        try:
            result = self._make_request('GET', 'status')
            if result:
                self.write({
                    'gss_server_status': 'online',
                })
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': _('Connection successful!'),
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                raise UserError(_('No response from server'))
                
        except Exception as e:
            self.write({'gss_server_status': 'error'})
            raise UserError(_('Connection failed: %s') % str(e))
    
    def sync_repositories(self):
        """Sync repositories from the GitHub Sync Server."""
        self.ensure_one()
        try:
            result = self._make_request('GET', 'repositories')
            if result and result.get('success'):
                repositories = result.get('data', [])
                
                for repo_data in repositories:
                    self._create_or_update_repository(repo_data)
                
                self.write({'gss_last_sync': fields.Datetime.now()})
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': _('Successfully synced %s repositories') % len(repositories),
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                raise UserError(_('Failed to sync repositories: %s') % result.get('message', 'Unknown error'))
                
        except Exception as e:
            raise
    
    def _create_or_update_repository(self, repo_data):
        """Create or update repository record."""
        external_id = repo_data.get('id')
        if not external_id:
            return
        
        repo = self.env['github.repository'].search([
            ('gr_external_id', '=', external_id),
            ('gr_server_id', '=', self.id)
        ], limit=1)
        
        vals = {
            'gr_name': repo_data.get('name', ''),
            'gr_external_id': external_id,
            'gr_server_id': self.id,
            'gr_url': repo_data.get('url', ''),
            'gr_branch': repo_data.get('branch', 'main'),
            'gr_local_path': repo_data.get('local_path', f'/repos/{repo_data.get("name", "")}'),
            'gr_status': repo_data.get('status', 'success'),
            'gr_last_pull': repo_data.get('last_pull'),
            'gr_description': repo_data.get('description', ''),
            'gr_private': repo_data.get('private', False),
        }
        
        if repo:
            repo.write(vals)
        else:
            self.env['github.repository'].create(vals)
    
    # ========================================================================
    # ACTION METHODS
    # ========================================================================
    
    def sync_logs(self):
        """Sync logs from the GitHub Sync Server."""
        self.ensure_one()
        try:
            result = self._make_request('GET', 'logs')
            if result and result.get('success'):
                logs = result.get('data', [])
                
                for log_data in logs:
                    self._create_or_update_log(log_data)
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': _('Successfully synced %s logs') % len(logs),
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                raise UserError(_('Failed to sync logs: %s') % result.get('message', 'Unknown error'))
                
        except Exception as e:
            raise
    
    def _create_or_update_log(self, log_data):
        """Create or update log record."""
        external_id = log_data.get('id')
        if not external_id:
            return
        
        log = self.env['github.sync.log'].search([
            ('gsl_external_id', '=', external_id),
            ('gsl_server_id', '=', self.id)
        ], limit=1)
        
        # Parse timestamp properly
        timestamp_str = log_data.get('timestamp')
        if timestamp_str:
            try:
                # Handle ISO format with or without timezone
                if 'T' in timestamp_str:
                    # Remove timezone info if present
                    if '+' in timestamp_str:
                        timestamp_str = timestamp_str.split('+')[0]
                    elif 'Z' in timestamp_str:
                        timestamp_str = timestamp_str.replace('Z', '')
                    # Convert ISO format to Odoo datetime format
                    timestamp = datetime.strptime(timestamp_str, '%Y-%m-%dT%H:%M:%S')
                else:
                    timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
            except (ValueError, TypeError):
                timestamp = fields.Datetime.now()
        else:
            timestamp = fields.Datetime.now()
        
        vals = {
            'gsl_external_id': external_id,
            'gsl_server_id': self.id,
            'gsl_time': timestamp,
            'gsl_operation': log_data.get('operation', 'sync'),
            'gsl_status': log_data.get('status', 'success'),
            'gsl_message': log_data.get('message', ''),
        }
        
        if log:
            log.write(vals)
        else:
            self.env['github.sync.log'].create(vals)
    
    def action_view_repositories(self):
        """Open repositories view filtered by this server."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Repositories - %s') % self.gss_name,
            'res_model': 'github.repository',
            'view_mode': 'tree,form',
            'domain': [('gr_server_id', '=', self.id)],
            'context': {'default_gr_server_id': self.id},
            'target': 'current',
        }
    
    def action_view_logs(self):
        """Open logs view filtered by this server."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Logs - %s') % self.gss_name,
            'res_model': 'github.sync.log',
            'view_mode': 'tree,form',
            'domain': [('gsl_server_id', '=', self.id)],
            'context': {'default_gsl_server_id': self.id},
            'target': 'current',
        }