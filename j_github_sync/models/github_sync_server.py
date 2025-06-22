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
            if record.gss_server_url:
                if not record.gss_server_url.startswith(('http://', 'https://')):
                    raise ValidationError(_('Server URL must start with http:// or https://'))
                # Ensure URL ends with slash for proper API handling
                if not record.gss_server_url.endswith('/'):
                    record.gss_server_url = record.gss_server_url + '/'

    # ========================================================================
    # API METHODS
    # ========================================================================
    
    def _get_headers(self):
        """Get API headers with authentication."""
        self.ensure_one()
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'Odoo-GitHub-Sync-Client/1.0'
        }
        if self.gss_api_key:
            headers['Authorization'] = f'Bearer {self.gss_api_key}'
        return headers
    
    def _get_api_url(self, endpoint):
        """Get full API URL for endpoint."""
        self.ensure_one()
        base_url = self.gss_server_url.rstrip('/')
        endpoint = endpoint.lstrip('/')
        
        # Handle cases where the base URL already includes /api
        if '/api' in base_url:
            return f"{base_url}/{endpoint}"
        else:
            return f"{base_url}/api/{endpoint}"
    
    def _make_request(self, method, endpoint, data=None, params=None):
        """Make HTTP request to the API."""
        self.ensure_one()
        
        url = self._get_api_url(endpoint)
        headers = self._get_headers()
        
        try:
            _logger.info(f"Making {method} request to {url}")
            _logger.info(f"Headers: {headers}")
            if data:
                _logger.info(f"Request data: {data}")
            
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=data,
                params=params,
                timeout=60,
                verify=False,
                allow_redirects=True
            )
            
            _logger.info(f"Response status: {response.status_code}")
            
            if response.status_code in [200, 201]:
                try:
                    result = response.json()
                    _logger.info(f"API Response: {result}")
                    self._log_request_details(method, endpoint, data, result, response_code=response.status_code)
                    return result
                except ValueError as e:
                    # Handle non-JSON responses
                    _logger.warning(f"Non-JSON response: {response.text[:200]}")
                    result = {'success': True, 'data': response.text, 'raw_response': True}
                    self._log_request_details(method, endpoint, data, result, response_code=response.status_code)
                    return result
            elif response.status_code in [401, 403]:
                self._log_request_details(method, endpoint, data, None, response_code=response.status_code, error='Authentication failed')
                raise UserError(_('Authentication failed. Please check your API key.'))
            elif response.status_code == 404:
                self._log_request_details(method, endpoint, data, None, response_code=response.status_code, error='Endpoint not found')
                raise UserError(_('Endpoint not found: %s. Please verify the server URL and API endpoints.') % endpoint)
            elif response.status_code == 500:
                self._log_request_details(method, endpoint, data, None, response_code=response.status_code, error='Internal server error')
                raise UserError(_('Server error (500). The GitHub Sync Server encountered an internal error.'))
            else:
                try:
                    error_data = response.json()
                    error_message = error_data.get('message', f'HTTP {response.status_code}')
                except:
                    error_message = f'HTTP {response.status_code}: {response.text[:200]}'
                self._log_request_details(method, endpoint, data, None, response_code=response.status_code, error=error_message)
                raise UserError(_('API Error: %s') % error_message)
                
        except requests.exceptions.ConnectTimeout as e:
            self._log_request_details(method, endpoint, data, None, error=str(e))
            raise UserError(_('Connection timeout. The server at %s is not responding within 60 seconds. Please check if the server is running and accessible.') % self.gss_server_url)
        except requests.exceptions.ConnectionError as e:
            self._log_request_details(method, endpoint, data, None, error=str(e))
            error_msg = str(e).lower()
            if 'name or service not known' in error_msg or 'nodename nor servname provided' in error_msg:
                raise UserError(_('Cannot resolve hostname. Please verify the server URL: %s\n\nCommon issues:\n- Check if the IP address is correct\n- Ensure the server is accessible from your network\n- Try using the full URL with protocol (http:// or https://)') % self.gss_server_url)
            elif 'connection refused' in error_msg:
                raise UserError(_('Connection refused. The server is not accepting connections on %s\n\nPossible causes:\n- Server is not running\n- Port is blocked by firewall\n- Service is not listening on the specified port') % self.gss_server_url)
            elif 'timeout' in error_msg:
                raise UserError(_('Network timeout connecting to %s\n\nTry:\n- Check network connectivity\n- Verify server is responsive\n- Contact your network administrator') % self.gss_server_url)
            else:
                raise UserError(_('Connection failed to %s\n\nError details: %s\n\nPlease verify:\n- Server URL is correct\n- Server is running and accessible\n- Network allows outbound connections') % (self.gss_server_url, str(e)))
        except requests.exceptions.Timeout as e:
            self._log_request_details(method, endpoint, data, None, error=str(e))
            raise UserError(_('Request timeout after 60 seconds. The server may be overloaded or network is slow.'))
        except requests.exceptions.RequestException as e:
            self._log_request_details(method, endpoint, data, None, error=str(e))
            raise UserError(_('Request failed: %s\n\nPlease check your network connection and server availability.') % str(e))
        
        return None
    
    def _log_request_details(self, method, endpoint, request_data, response_data, response_code=None, error=None):
        """Log request and response details."""
        if response_data:
            # Store the raw response as-is
            self.write({'gss_last_request_details': json.dumps(response_data, indent=2)})
        elif error:
            # Store error information
            error_details = {
                'error': error,
                'endpoint': endpoint,
                'method': method,
                'response_code': response_code
            }
            self.write({'gss_last_request_details': json.dumps(error_details, indent=2)})
    

    
    def test_connection(self):
        """Test connection to the GitHub Sync Server."""
        self.ensure_one()
        
        if not self.gss_server_url:
            raise UserError(_('Please configure the server URL first.'))
            
        try:
            _logger.info(f"Testing connection to {self.gss_server_url}")
            
            # First try a simple connectivity test
            test_url = self.gss_server_url.rstrip('/')
            _logger.info(f"Testing basic connectivity to {test_url}")
            
            try:
                # Simple connectivity check
                basic_response = requests.get(test_url, timeout=30, verify=False)
                _logger.info(f"Basic connectivity test - Status: {basic_response.status_code}")
            except Exception as basic_error:
                _logger.error(f"Basic connectivity failed: {basic_error}")
            
            # Now try the API status endpoint
            result = self._make_request('GET', 'status')
            
            if result:
                self.write({
                    'gss_server_status': 'online',
                    'gss_last_sync': fields.Datetime.now()
                })
                
                # Extract useful info from response
                message = _('Connection successful!\n\nServer is responding to API requests.')
                
                if isinstance(result, dict):
                    if isinstance(result.get('data'), dict):
                        status_info = result.get('data', {})
                        server_version = status_info.get('version', 'Unknown')
                        server_status = status_info.get('status', 'Unknown')
                        uptime = status_info.get('uptime', 'Unknown')
                        
                        message = _('Connection successful!\n\nServer Status: %s\nVersion: %s\nUptime: %s') % (server_status, server_version, uptime)
                    elif result.get('status'):
                        # Handle simple status response
                        message = _('Connection successful!\n\nServer Status: %s') % result.get('status')
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': message,
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                self.write({'gss_server_status': 'error'})
                raise UserError(_('No response from server. Please verify:\n- Server URL is correct\n- GitHub Sync Server is running\n- API endpoints are available'))
                
        except Exception as e:
            self.write({'gss_server_status': 'error'})
            # Re-raise the exception to show the detailed error message
            raise
    
    def sync_repositories(self):
        """Sync repositories from the GitHub Sync Server."""
        self.ensure_one()
        try:
            result = self._make_request('GET', 'repositories')
            
            # Handle different response formats
            repositories = []
            if isinstance(result, list):
                # Direct list response
                repositories = result
            elif isinstance(result, dict):
                if result.get('success'):
                    repositories = result.get('data', [])
                else:
                    raise UserError(_('Failed to sync repositories: %s') % result.get('message', 'Unknown error'))
            else:
                raise UserError(_('Invalid response format from server'))
            
            if repositories:
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
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': _('No repositories found on server'),
                        'type': 'info',
                        'sticky': False,
                    }
                }
                
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
        
        # Parse last_pull timestamp properly - preserve actual server timestamp
        last_pull = None
        last_pull_str = repo_data.get('last_pull') or repo_data.get('last_sync') or repo_data.get('updated_at')
        
        if last_pull_str:
            try:
                last_pull_str = str(last_pull_str).strip()
                _logger.info(f"Parsing repository last_pull: '{last_pull_str}'")
                
                # Handle different timestamp formats from server
                if 'T' in last_pull_str:
                    # ISO format: 2025-06-22T07:50:00 or 2025-06-22T07:50:00Z
                    if last_pull_str.endswith('Z'):
                        last_pull_str = last_pull_str[:-1]
                    if '+' in last_pull_str:
                        last_pull_str = last_pull_str.split('+')[0]
                    if '.' in last_pull_str:
                        last_pull_str = last_pull_str.split('.')[0]
                    last_pull = datetime.strptime(last_pull_str, '%Y-%m-%dT%H:%M:%S')
                elif '-' in last_pull_str and ':' in last_pull_str:
                    # Standard format: 2025-06-22 07:50 or 2025-06-22 07:50:00
                    if '.' in last_pull_str:
                        last_pull_str = last_pull_str.split('.')[0]
                    if len(last_pull_str.split(':')) == 2:
                        # Add seconds if missing: 2025-06-22 07:50
                        last_pull_str += ':00'
                    last_pull = datetime.strptime(last_pull_str, '%Y-%m-%d %H:%M:%S')
                else:
                    # Try other formats
                    for fmt in ['%Y-%m-%d %H:%M', '%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M']:
                        try:
                            last_pull = datetime.strptime(last_pull_str, fmt)
                            break
                        except ValueError:
                            continue
                
                if last_pull:
                    _logger.info(f"Successfully parsed last_pull: {last_pull}")
                    
            except (ValueError, TypeError) as e:
                _logger.error(f"Failed to parse last_pull timestamp '{last_pull_str}': {e}")
                last_pull = None
        
        # Map and validate repository status - preserve actual server status
        raw_status = repo_data.get('status', '').lower().strip()
        _logger.info(f"Raw repository status from server: '{raw_status}'")
        
        # Map server statuses to Odoo repository statuses
        status_mapping = {
            'success': 'success',
            'error': 'error',
            'warning': 'warning',
            'pending': 'pending',
            'syncing': 'syncing',
            'active': 'success',       # Map active to success
            'healthy': 'success',      # Map healthy to success
            'online': 'success',       # Map online to success
            'ready': 'success',        # Map ready to success
            'failed': 'error',         # Map failed to error
            'offline': 'error',        # Map offline to error
            'inactive': 'warning',     # Map inactive to warning
            'disabled': 'warning',     # Map disabled to warning
        }
        
        status = status_mapping.get(raw_status, raw_status)
        valid_statuses = ['success', 'error', 'warning', 'pending', 'syncing']
        
        if status not in valid_statuses:
            _logger.warning(f"Unknown repository status '{raw_status}', mapping to 'success'")
            status = 'success'  # Default to success instead of pending for repositories
        
        _logger.info(f"Final repository status: '{status}'")
        
        vals = {
            'gr_name': repo_data.get('name', ''),
            'gr_external_id': external_id,
            'gr_server_id': self.id,
            'gr_url': repo_data.get('url', ''),
            'gr_branch': repo_data.get('branch', 'main'),
            'gr_local_path': repo_data.get('local_path', f'/repos/{repo_data.get("name", "")}'),
            'gr_status': status,
            'gr_last_pull': last_pull,
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
            
            # Handle different response formats
            logs = []
            if isinstance(result, list):
                # Direct list response
                logs = result
            elif isinstance(result, dict):
                if result.get('success'):
                    logs = result.get('data', [])
                else:
                    raise UserError(_('Failed to sync logs: %s') % result.get('message', 'Unknown error'))
            else:
                raise UserError(_('Invalid response format from server'))
            
            if logs:
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
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': _('No logs found on server'),
                        'type': 'info',
                        'sticky': False,
                    }
                }
                
        except Exception as e:
            raise
    
    def _create_or_update_log(self, log_data):
        """Create or update log record."""
        # Handle different log data formats
        if not isinstance(log_data, dict):
            _logger.warning(f"Invalid log data format: {type(log_data)}")
            return
            
        external_id = log_data.get('id') or log_data.get('log_id') or log_data.get('external_id')
        if not external_id:
            _logger.warning(f"No external ID found in log data: {log_data}")
            return
        
        log = self.env['github.sync.log'].search([
            ('gsl_external_id', '=', str(external_id)),
            ('gsl_server_id', '=', self.id)
        ], limit=1)
        
        # Parse timestamp properly - use actual server timestamp, not sync time
        timestamp_str = log_data.get('timestamp') or log_data.get('time') or log_data.get('created_at')
        timestamp = None
        
        if timestamp_str:
            try:
                timestamp_str = str(timestamp_str).strip()
                _logger.info(f"Parsing timestamp: '{timestamp_str}'")
                
                # Handle different timestamp formats from server
                if 'T' in timestamp_str:
                    # ISO format: 2025-06-22T10:30:00 or 2025-06-22T10:30:00Z
                    if timestamp_str.endswith('Z'):
                        timestamp_str = timestamp_str[:-1]
                    if '+' in timestamp_str:
                        timestamp_str = timestamp_str.split('+')[0]
                    if '.' in timestamp_str:
                        # Handle microseconds: 2025-06-22T10:30:00.123
                        timestamp_str = timestamp_str.split('.')[0]
                    timestamp = datetime.strptime(timestamp_str, '%Y-%m-%dT%H:%M:%S')
                elif '-' in timestamp_str and ':' in timestamp_str:
                    # Standard format: 2025-06-22 10:30:00
                    if '.' in timestamp_str:
                        timestamp_str = timestamp_str.split('.')[0]
                    timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                else:
                    # Try other common formats
                    for fmt in ['%Y-%m-%d %H:%M', '%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M']:
                        try:
                            timestamp = datetime.strptime(timestamp_str, fmt)
                            break
                        except ValueError:
                            continue
                
                if timestamp:
                    _logger.info(f"Successfully parsed timestamp: {timestamp}")
                else:
                    raise ValueError(f"No matching format found for: {timestamp_str}")
                    
            except (ValueError, TypeError) as e:
                _logger.error(f"Failed to parse timestamp '{timestamp_str}': {e}")
                # Only use current time as absolute fallback
                timestamp = fields.Datetime.now()
                _logger.warning(f"Using current time as fallback: {timestamp}")
        else:
            _logger.warning("No timestamp found in log data, using current time")
            timestamp = fields.Datetime.now()
        
        # Find repository if referenced
        repository_id = None
        repo_ref = (log_data.get('repository_id') or 
                   log_data.get('repository_name') or 
                   log_data.get('repo_id') or 
                   log_data.get('repo_name'))
        if repo_ref:
            repository = self.env['github.repository'].search([
                '|',
                ('gr_external_id', '=', str(repo_ref)),
                ('gr_name', '=', str(repo_ref)),
                ('gr_server_id', '=', self.id)
            ], limit=1)
            if repository:
                repository_id = repository.id
        
        # Map and validate operation value - preserve actual server operation
        # Server uses 'operation_type' field, not 'operation'
        raw_operation = log_data.get('operation_type', log_data.get('operation', '')).lower().strip()
        _logger.info(f"Raw operation from server (operation_type): '{raw_operation}'")
        
        # Map server operations to Odoo operations (preserve original values)
        operation_mapping = {
            'webhook': 'webhook',
            'pull': 'pull', 
            'clone': 'clone',
            'restart': 'restart',
            'push': 'webhook',  # Map push events to webhook
            'sync': 'pull',     # Map generic sync to pull
            'update': 'pull',   # Map update to pull
        }
        
        operation = operation_mapping.get(raw_operation, raw_operation)
        valid_operations = ['pull', 'clone', 'restart', 'webhook']
        
        if operation not in valid_operations:
            _logger.warning(f"Unknown operation '{raw_operation}', defaulting to 'pull'")
            operation = 'pull'  # Default to pull for unknown operations
        
        _logger.info(f"Final operation: '{operation}'")
        
        # Map and validate status value - preserve actual server status
        raw_status = log_data.get('status', '').lower().strip()
        _logger.info(f"Raw status from server: '{raw_status}'")
        
        # Map server statuses to Odoo statuses (only success, error, warning)
        status_mapping = {
            'success': 'success',
            'error': 'error',
            'warning': 'warning', 
            'pending': 'warning',      # Map pending to warning
            'syncing': 'warning',      # Map syncing to warning
            'in_progress': 'warning',  # Map in_progress to warning
            'running': 'warning',      # Map running to warning
            'failed': 'error',         # Map failed to error
            'completed': 'success',    # Map completed to success
            'finished': 'success',     # Map finished to success
        }
        
        status = status_mapping.get(raw_status, raw_status)
        valid_statuses = ['success', 'error', 'warning']
        
        if status not in valid_statuses:
            _logger.warning(f"Unknown status '{raw_status}', mapping to 'warning'")
            status = 'warning'
        
        _logger.info(f"Final status: '{status}'")
        
        vals = {
            'gsl_external_id': str(external_id),
            'gsl_server_id': self.id,
            'gsl_time': timestamp,
            'gsl_operation': operation,
            'gsl_status': status,
            'gsl_message': str(log_data.get('message', '')),
            'gsl_details': json.dumps(log_data.get('details', {}), indent=2) if log_data.get('details') else '',
        }
        
        # Add repository_id only if found
        if repository_id:
            vals['gsl_repository_id'] = repository_id
        
        try:
            if log:
                log.write(vals)
            else:
                self.env['github.sync.log'].create(vals)
        except Exception as e:
            _logger.error(f"Failed to create/update log record: {e}")
            _logger.error(f"Log data: {log_data}")
            _logger.error(f"Processed vals: {vals}")
            raise
    
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