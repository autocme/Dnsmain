#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import requests
import logging
import json
from datetime import datetime
import urllib3
from typing import Optional, Union, Any

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_logger = logging.getLogger(__name__)


class PortainerServer(models.Model):
    _name = 'j_portainer.server'
    _description = 'Portainer Server'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    def _parse_date_value(self, date_value: Any) -> Optional[datetime]:
        """Parse date value from API response

        Handles different date formats from the Portainer API including:
        - ISO format strings (2022-01-01T00:00:00Z)
        - Integer timestamps
        - None values

        Args:
            date_value: Date value from API response

        Returns:
            naive datetime object or None if value cannot be parsed

        Note:
            Returns naive datetime objects (without timezone info) as required by Odoo
        """
        if not date_value:
            return None

        # First try with fields.Datetime which is safer for Odoo
        if isinstance(date_value, str):
            try:
                # Simple format without timezone for Datetime fields
                if 'T' in date_value:
                    # Format: 2025-03-04T22:12:54.389453136Z -> 2025-03-04 22:12:54
                    simple_date = date_value.split('.')[0].replace('T', ' ')
                    return fields.Datetime.from_string(simple_date)
            except Exception:
                pass

        # Fall back to more complex parsing if needed
        try:
            if isinstance(date_value, str):
                # Handle ISO format string with timezone
                dt_with_tz = datetime.fromisoformat(date_value.replace('Z', '+00:00'))
                # Return naive datetime (no timezone info) for Odoo compatibility
                return dt_with_tz.replace(tzinfo=None)
            elif isinstance(date_value, (int, float)):
                # Use the safe timestamp parsing method instead
                return self._safe_parse_timestamp(date_value)
            else:
                _logger.warning(f"Unsupported date format: {date_value} ({type(date_value)})")
                return None
        except Exception as e:
            _logger.warning(f"Error parsing date value {date_value}: {str(e)}")

            # Last attempt for ISO-format with Z timezone
            if isinstance(date_value, str) and 'T' in date_value and date_value.endswith('Z'):
                try:
                    # Just extract YYYY-MM-DD HH:MM:SS without timezone or microseconds
                    date_parts = date_value.replace('Z', '').split('.')
                    simple_str = date_parts[0].replace('T', ' ')
                    return datetime.strptime(simple_str, '%Y-%m-%d %H:%M:%S')
                except Exception as simple_error:
                    _logger.warning(f"Simple date parsing also failed: {str(simple_error)}")

            return None

    def _safe_parse_timestamp(self, timestamp_value):
        """Safely parse a timestamp value to a datetime object

        Args:
            timestamp_value: A timestamp value that could be an integer, float, or string

        Returns:
            naive datetime object (without timezone info) or current time if parsing fails

        Note:
            This method handles large timestamp values that could cause integer overflow
            Always returns naive datetime objects (without timezone info) as required by Odoo
        """
        try:
            # Check if timestamp_value is an integer or float and is within safe range
            if isinstance(timestamp_value, (int, float)):
                # If timestamp is too large (e.g., nanoseconds), convert to seconds
                if timestamp_value > 2147483647:  # Max safe 32-bit integer
                    timestamp_value = timestamp_value / 1000000000  # Convert nanoseconds to seconds

                # If still too large, use a fixed date
                if timestamp_value > 2147483647:
                    return datetime.now().replace(tzinfo=None)

                return datetime.fromtimestamp(timestamp_value)

            # If it's a string, try to parse it as a date string
            elif isinstance(timestamp_value, str):
                try:
                    # Parse ISO format string, then remove timezone
                    dt = datetime.fromisoformat(timestamp_value.replace('Z', '+00:00').replace('z', '+00:00'))
                    # Return naive datetime (remove timezone)
                    return dt.replace(tzinfo=None)
                except ValueError:
                    # Try parsing as a float and convert to timestamp
                    try:
                        float_value = float(timestamp_value)
                        return self._safe_parse_timestamp(float_value)
                    except ValueError:
                        pass
        except Exception as e:
            _logger.warning(f"Error parsing timestamp {timestamp_value}: {str(e)}")

        # Default fallback to current time (naive datetime)
        return datetime.now().replace(tzinfo=None)

    name = fields.Char('Name', required=True, tracking=True)
    url = fields.Char('URL', required=True, tracking=True,
                      help="URL to Portainer server (e.g., https://portainer.example.com:9443)")
    api_key = fields.Char('API Key', required=True, tracking=True,
                          help="Portainer API key for authentication")
    verify_ssl = fields.Boolean('Verify SSL', default=False, tracking=True,
                                help="Verify SSL certificates when connecting (disable for self-signed certificates)")
    status = fields.Selection([
        ('unknown', 'Unknown'),
        ('connecting', 'Connecting'),
        ('connected', 'Connected'),
        ('error', 'Error')
    ], string='Status', default='unknown', readonly=True, tracking=True)
    last_sync = fields.Datetime('Last Synchronization', readonly=True, tracking=True)
    error_message = fields.Text('Error Message', readonly=True)
    portainer_version = fields.Char('Portainer Version', readonly=True)
    portainer_info = fields.Text('Server Info', readonly=True)
    environment_count = fields.Integer('Environments', readonly=True)

    # API logs relationship
    api_log_ids = fields.One2many('j_portainer.api_log', 'server_id', string='API Logs')
    api_log_count = fields.Integer('API Log Count', compute='_compute_api_log_count')

    def _compute_api_log_count(self):
        """Compute the number of API logs related to this server"""
        for server in self:
            server.api_log_count = self.env['j_portainer.api_log'].search_count([
                ('server_id', '=', server.id)
            ])

    def _compute_sync_schedules_count(self):
        """Compute the number of sync schedules configured for this server"""
        for server in self:
            server.sync_schedules_count = self.env['j_portainer.sync.schedule'].search_count([
                ('server_id', '=', server.id)
            ])

    def _compute_backup_history_count(self):
        """Compute the number of backup history records for this server"""
        for server in self:
            server.backup_history_count = self.env['j_portainer.backup.history'].search_count([
                ('server_id', '=', server.id)
            ])

    def _compute_backup_schedule_fields(self):
        """Compute backup schedule fields for form view"""
        for server in self:
            schedule = server.get_backup_schedule()
            server.backup_schedule_active = schedule.active if schedule else False
            server.backup_schedule_days = schedule.schedule_days if schedule else 1
            server.backup_schedule_password = schedule.backup_password if schedule else 'default_password_change_me'
            server.backup_schedule_last_backup = schedule.last_backup if schedule else False
            server.backup_schedule_next_backup = schedule.next_backup if schedule else False

    def _inverse_backup_schedule_active(self):
        """Update backup schedule active status"""
        for server in self:
            schedule = server.get_backup_schedule()
            if schedule:
                schedule.active = server.backup_schedule_active

    def _inverse_backup_schedule_days(self):
        """Update backup schedule days"""
        for server in self:
            schedule = server.get_backup_schedule()
            if schedule and server.backup_schedule_days:
                schedule.schedule_days = server.backup_schedule_days

    def _inverse_backup_schedule_password(self):
        """Update backup schedule password"""
        for server in self:
            schedule = server.get_backup_schedule()
            if schedule and server.backup_schedule_password:
                schedule.backup_password = server.backup_schedule_password

    # Related Resources
    container_ids = fields.One2many('j_portainer.container', 'server_id', string='Containers')
    image_ids = fields.One2many('j_portainer.image', 'server_id', string='Images')
    volume_ids = fields.One2many('j_portainer.volume', 'server_id', string='Volumes')
    network_ids = fields.One2many('j_portainer.network', 'server_id', string='Networks')
    template_ids = fields.One2many('j_portainer.template', 'server_id', string='Templates')
    custom_template_ids = fields.One2many('j_portainer.customtemplate', 'server_id', string='Custom Templates')
    stack_ids = fields.One2many('j_portainer.stack', 'server_id', string='Stacks')
    environment_ids = fields.One2many('j_portainer.environment', 'server_id', string='Environments')

    # Sync Schedule relationship
    sync_schedule_ids = fields.One2many('j_portainer.sync.schedule', 'server_id', string='Sync Schedules')
    sync_schedules_count = fields.Integer('Sync Schedules Count', compute='_compute_sync_schedules_count')

    # Backup Schedule relationship (one-to-one)
    backup_schedule_id = fields.One2many('j_portainer.backup.schedule', 'server_id', string='Backup Schedule')
    backup_history_ids = fields.One2many('j_portainer.backup.history', 'server_id', string='Backup History')
    backup_history_count = fields.Integer('Backup History Count', compute='_compute_backup_history_count')

    # Backup Schedule computed fields for form view
    backup_schedule_active = fields.Boolean('Backup Schedule Active', compute='_compute_backup_schedule_fields',
                                            inverse='_inverse_backup_schedule_active')
    backup_schedule_days = fields.Integer('Backup Schedule Days', compute='_compute_backup_schedule_fields',
                                          inverse='_inverse_backup_schedule_days')
    backup_schedule_password = fields.Char('Backup Schedule Password', compute='_compute_backup_schedule_fields',
                                           inverse='_inverse_backup_schedule_password')
    backup_schedule_last_backup = fields.Datetime('Last Scheduled Backup', compute='_compute_backup_schedule_fields')
    backup_schedule_next_backup = fields.Datetime('Next Scheduled Backup', compute='_compute_backup_schedule_fields')

    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'Server name must be unique!')
    ]

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            record.test_connection()
            # Auto-create backup schedule for each new server
            record._create_default_backup_schedule()
        return records

    def write(self, vals):
        # If connection parameters changed, test connection
        if 'url' in vals or 'api_key' in vals or 'verify_ssl' in vals:
            result = super().write(vals)
            self.test_connection()
            return result
        return super().write(vals)

    def test_connection(self):
        """Test connection to the Portainer server"""
        self.ensure_one()

        try:
            self.status = 'connecting'
            self._cr.commit()  # Commit the transaction to update the UI

            # Make API request to get system status
            response = self._make_api_request('/api/system/status', 'GET')

            if response.status_code == 200:
                status_data = response.json()
                version = status_data.get('Version', 'Unknown')

                # Get additional system info
                info_response = self._make_api_request('/api/system/info', 'GET')
                info_data = info_response.json() if info_response.status_code == 200 else {}

                # Get endpoints (environments) count
                endpoints_response = self._make_api_request('/api/endpoints', 'GET')
                endpoints_data = endpoints_response.json() if endpoints_response.status_code == 200 else []

                # Update server info
                self.write({
                    'status': 'connected',
                    'last_sync': fields.Datetime.now(),
                    'error_message': False,
                    'portainer_version': version,
                    'portainer_info': json.dumps(info_data, indent=2) if info_data else '',
                    'environment_count': len(endpoints_data),
                })

                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Connection Successful'),
                        'message': _('Successfully connected to Portainer server (version %s)') % version,
                        'sticky': False,
                        'type': 'success',
                    }
                }
            else:
                error_msg = _("API Error: %s") % response.text
                self.write({
                    'status': 'error',
                    'error_message': error_msg
                })
                raise UserError(error_msg)

        except Exception as e:
            _logger.error(f"Connection error: {str(e)}")
            self.write({
                'status': 'error',
                'error_message': str(e)
            })
            raise UserError(_("Connection error: %s") % str(e))

    def _get_api_key_header(self):
        """Get the API key header for authentication

        Returns:
            str: API key header value
        """
        if not self.api_key:
            return None

        # Format header value for X-API-Key authentication
        return f"{self.api_key}"

    def _make_api_request(self, endpoint, method='GET', data=None, params=None, headers=None, use_multipart=False,
                          environment_id=None, timeout=None):
        """Make a request to the Portainer API

        Args:
            endpoint (str): API endpoint (e.g., '/api/endpoints')
            method (str): HTTP method (GET, POST, PUT, DELETE)
            data (dict, optional): Request payload for POST/PUT
            params (dict, optional): URL parameters
            headers (dict, optional): Additional headers to include with the request
            use_multipart (bool, optional): Whether to use multipart form data instead of JSON
            environment_id (int, optional): Environment ID related to this request (for logging)
            timeout (int, optional): Custom timeout in seconds (default: 15 for GET/DELETE, 30 for POST/PUT multipart)

        Returns:
            requests.Response: API response
        """
        url = self.url.rstrip('/') + endpoint
        start_time = datetime.now()
        environment_name = None

        # Try to determine environment name if environment_id is provided
        if environment_id:
            env = self.env['j_portainer.environment'].search([
                ('server_id', '=', self.id),
                ('environment_id', '=', environment_id)
            ], limit=1)
            if env:
                environment_name = env.name

        # If environment_id is in the URL but not provided as param, try to extract it
        elif not environment_id:
            # Check for common URL patterns where environment ID is present
            # Pattern 1: /api/endpoints/3/... (environment ID directly in path)
            # Pattern 2: /api/endpoints/3      (environment ID is the last part)
            # Pattern 3: /api/stacks?endpointId=3 (environment ID in query string)
            try:
                # First try extracting from path
                if '/endpoints/' in endpoint:
                    url_parts = endpoint.split('/')
                    if 'endpoints' in url_parts:
                        endpoints_index = url_parts.index('endpoints')
                        if endpoints_index + 1 < len(url_parts) and url_parts[endpoints_index + 1].isdigit():
                            extracted_env_id = int(url_parts[endpoints_index + 1])
                            env = self.env['j_portainer.environment'].search([
                                ('server_id', '=', self.id),
                                ('environment_id', '=', extracted_env_id)
                            ], limit=1)
                            if env:
                                environment_id = extracted_env_id
                                environment_name = env.name

                # Then try extracting from query parameters
                elif params and ('endpointId' in params or 'environmentId' in params):
                    param_env_id = params.get('endpointId') or params.get('environmentId')
                    if param_env_id and (isinstance(param_env_id, int) or (
                            isinstance(param_env_id, str) and param_env_id.isdigit())):
                        extracted_env_id = int(param_env_id)
                        env = self.env['j_portainer.environment'].search([
                            ('server_id', '=', self.id),
                            ('environment_id', '=', extracted_env_id)
                        ], limit=1)
                        if env:
                            environment_id = extracted_env_id
                            environment_name = env.name
            except Exception as e:
                _logger.debug(f"Could not extract environment ID from URL: {str(e)}")

        # Default headers
        request_headers = {
            'X-API-Key': self._get_api_key_header(),
        }

        # Set Content-Type if not using multipart (for multipart it's set automatically)
        if not use_multipart and 'Content-Type' not in request_headers:
            request_headers['Content-Type'] = 'application/json'

        # Update with any additional headers
        if headers:
            request_headers.update(headers)

        # Prepare log data
        log_vals = {
            'server_id': self.id,
            'endpoint': endpoint,
            'method': method,
            'environment_id': environment_id if environment_id else False,
            'environment_name': environment_name if environment_name else '',
            'request_date': start_time,
        }

        # Sanitize and log request data (for both data and params)
        request_log_data = {}

        # Add JSON body data for logging if present
        if data and not use_multipart:
            # Create a copy of data to avoid modifying the original
            log_data = data.copy() if isinstance(data, dict) else data

            # Mask sensitive data if it's a dictionary
            if isinstance(log_data, dict):
                if 'api_key' in log_data:
                    log_data['api_key'] = '******'
                if 'password' in log_data:
                    log_data['password'] = '******'
                if 'apiKey' in log_data:
                    log_data['apiKey'] = '******'

            request_log_data['body'] = log_data

        # Add query parameters for logging if present
        if params:
            log_params = params.copy() if isinstance(params, dict) else params

            # Mask sensitive data in params if it's a dictionary
            if isinstance(log_params, dict):
                if 'api_key' in log_params:
                    log_params['api_key'] = '******'
                if 'apiKey' in log_params:
                    log_params['apiKey'] = '******'

            request_log_data['params'] = log_params

        # Include URL in log data
        request_log_data['url'] = url

        # Add HTTP method info
        request_log_data['method'] = method

        # Set the request_data field with all captured information
        log_vals['request_data'] = json.dumps(request_log_data, indent=2) if request_log_data else None

        # Create API log record
        api_log = self.env['j_portainer.api_log'].sudo().create(log_vals)

        try:
            _logger.debug(f"Making {method} request to {url}")

            # Set default timeouts based on method and use_multipart, or use custom timeout
            if timeout is None:
                if use_multipart:
                    request_timeout = 60  # Longer timeout for multipart uploads
                elif method in ['POST', 'PUT']:
                    request_timeout = 45  # Longer timeout for POST/PUT operations
                else:
                    request_timeout = 30  # Standard timeout for GET/DELETE
            else:
                request_timeout = timeout

            if method == 'GET':
                response = requests.get(url, headers=request_headers, params=params,
                                        verify=self.verify_ssl, timeout=request_timeout)
            elif method == 'POST':
                if use_multipart:
                    _logger.debug(f"POST request with multipart data")
                    response = requests.post(url, headers=request_headers, data=data,
                                             verify=self.verify_ssl, timeout=request_timeout)
                else:
                    # Include params in debug log to see what's being sent
                    _logger.debug(f"POST request data: {json.dumps(data, indent=2) if data else None}")
                    _logger.debug(f"POST request params: {params}")
                    # Include params in the POST request for operations like stack start/stop
                    response = requests.post(url, headers=request_headers, json=data, params=params,
                                             verify=self.verify_ssl, timeout=request_timeout)
            elif method == 'PUT':
                if use_multipart:
                    _logger.debug(f"PUT request with multipart data")
                    response = requests.put(url, headers=request_headers, data=data,
                                            verify=self.verify_ssl, timeout=request_timeout)
                else:
                    response = requests.put(url, headers=request_headers, json=data,
                                            verify=self.verify_ssl, timeout=request_timeout)
            elif method == 'DELETE':
                response = requests.delete(url, headers=request_headers, params=params,
                                           verify=self.verify_ssl, timeout=request_timeout)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            # Calculate response time
            end_time = datetime.now()
            response_time_ms = int((end_time - start_time).total_seconds() * 1000)

            # Create structured response log with enhanced information
            response_log_data = {
                'status_code': response.status_code,
                'headers': dict(response.headers),
                'url': response.url
            }

            # Process and format response data for logging
            response_data = ""
            try:
                # Process response body based on content type
                if response.status_code in [204, 304]:  # No content or Not modified
                    response_log_data['body'] = f"Empty response body (status {response.status_code})"
                else:
                    try:
                        # Try to parse as JSON
                        response_json = response.json()
                        response_log_data['body'] = response_json
                    except Exception:
                        # If not JSON, use text content (with length limit)
                        response_text = response.text[:5000] if response.text else ""
                        response_log_data['body'] = response_text

                # Convert the complete response log to JSON format for storage
                response_data = json.dumps(response_log_data, indent=2)
            except Exception as e:
                # Fallback in case of any error during response processing
                _logger.warning(f"Error formatting response data: {str(e)}")
                response_data = f"{{\"status_code\": {response.status_code}, \"error\": \"Error formatting response data: {str(e)}\"}}"

            # Update the log record with response info
            api_log.sudo().write({
                'status_code': response.status_code,
                'response_time_ms': response_time_ms,
                'response_data': response_data,  # Always log response data
                'error_message': response_data if response.status_code >= 300 else None,
            })

            _logger.debug(f"API response status: {response.status_code}")
            return response

        except requests.exceptions.ConnectionError as e:
            # Update log with error including request details
            end_time = datetime.now()
            response_time_ms = int((end_time - start_time).total_seconds() * 1000)

            # Create detailed error information
            error_data = {
                'error_type': 'ConnectionError',
                'url': url,
                'method': method,
                'message': str(e),
                'request': {
                    'params': params,
                    'headers': {k: v for k, v in request_headers.items() if k.lower() != 'x-api-key'},
                    'endpoint': endpoint
                }
            }

            api_log.sudo().write({
                'status_code': 0,
                'response_time_ms': response_time_ms,
                'error_message': json.dumps(error_data, indent=2),
                'response_data': json.dumps(error_data, indent=2)  # Include in response data for consistency
            })

            _logger.error(f"Connection error: {str(e)}")
            raise UserError(
                _("Connection error: Could not connect to Portainer server at %s. Please check the URL and network connectivity.") % self.url)

        except requests.exceptions.Timeout as e:
            # Update log with timeout error including request details
            end_time = datetime.now()
            response_time_ms = int((end_time - start_time).total_seconds() * 1000)

            # Create detailed error information
            error_data = {
                'error_type': 'Timeout',
                'url': url,
                'method': method,
                'message': str(e),
                'request': {
                    'params': params,
                    'headers': {k: v for k, v in request_headers.items() if k.lower() != 'x-api-key'},
                    'endpoint': endpoint
                }
            }

            api_log.sudo().write({
                'status_code': 0,
                'response_time_ms': response_time_ms,
                'error_message': json.dumps(error_data, indent=2),
                'response_data': json.dumps(error_data, indent=2)  # Include in response data for consistency
            })

            _logger.error("Connection timeout")
            raise UserError(_("Connection timeout: The request to Portainer server timed out. Please try again later."))

        except requests.exceptions.RequestException as e:
            # Update log with general request error including request details
            end_time = datetime.now()
            response_time_ms = int((end_time - start_time).total_seconds() * 1000)

            # Create detailed error information
            error_data = {
                'error_type': 'RequestException',
                'url': url,
                'method': method,
                'message': str(e),
                'request': {
                    'params': params,
                    'headers': {k: v for k, v in request_headers.items() if k.lower() != 'x-api-key'},
                    'endpoint': endpoint
                }
            }

            api_log.sudo().write({
                'status_code': 0,
                'response_time_ms': response_time_ms,
                'error_message': json.dumps(error_data, indent=2),
                'response_data': json.dumps(error_data, indent=2)  # Include in response data for consistency
            })

            _logger.error(f"Request error: {str(e)}")
            raise UserError(_("Request error: %s") % str(e))

    def sync_environments(self):
        """Sync environments from Portainer"""
        self.ensure_one()

        try:
            # Get all endpoints from Portainer
            response = self._make_api_request('/api/endpoints', 'GET')
            if response.status_code != 200:
                raise UserError(_("Failed to get environments: %s") % response.text)

            environments = response.json()
            synced_env_ids = []  # Track which environment IDs we've synced
            created_count = 0
            updated_count = 0

            for env in environments:
                env_id = env.get('Id')
                env_name = env.get('Name', 'Unknown')

                # Get endpoint details
                details_response = self._make_api_request(f'/api/endpoints/{env_id}', 'GET', environment_id=env_id)
                details = details_response.json() if details_response.status_code == 200 else {}

                # Check if environment already exists in Odoo
                existing_env = self.env['j_portainer.environment'].search([
                    ('server_id', '=', self.id),
                    ('environment_id', '=', env_id)
                ], limit=1)

                # Prepare environment data
                env_data = {
                    'server_id': self.id,
                    'environment_id': env_id,
                    'name': env_name,
                    'url': env.get('URL', ''),
                    'status': 'up' if env.get('Status') == 1 else 'down',
                    'type': str(env.get('Type', 1)),  # Convert to string for selection field
                    'public_url': env.get('PublicURL', ''),
                    'group_id': env.get('GroupId'),
                    'group_name': env.get('GroupName', ''),
                    'tags': ','.join(env.get('Tags', [])) if isinstance(env.get('Tags', []), list) else '',
                    'details': json.dumps(details, indent=2) if details else '',
                }

                if existing_env:
                    # Update existing environment
                    existing_env.write(env_data)
                    updated_count += 1
                    synced_env_ids.append(existing_env.id)
                else:
                    # Create new environment
                    new_env = self.env['j_portainer.environment'].create(env_data)
                    created_count += 1
                    synced_env_ids.append(new_env.id)

            # Mark environments that no longer exist in Portainer as inactive
            # Instead of deleting them (which would break foreign key constraints)
            obsolete_envs = self.environment_ids.filtered(lambda e: e.id not in synced_env_ids)
            if obsolete_envs:
                obsolete_envs.write({'active': False})
                _logger.info(f"Marked {len(obsolete_envs)} obsolete environments as inactive")

            # Update environment-specific last_sync timestamps
            now = fields.Datetime.now()
            synced_environments = self.env['j_portainer.environment'].browse(synced_env_ids)
            if synced_environments:
                synced_environments.write({'last_sync': now})

            self.write({
                'last_sync': now,
                'environment_count': len(environments)
            })

            _logger.info(
                f"Environment sync complete: {len(environments)} total environments, {created_count} created, {updated_count} updated")

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Environments Synchronized'),
                    'message': _('%d environments found') % len(environments),
                    'sticky': False,
                    'type': 'success',
                }
            }

        except Exception as e:
            _logger.error(f"Error syncing environments: {str(e)}")
            raise UserError(_("Error syncing environments: %s") % str(e))

    def sync_containers(self, environment_id=None):
        """Sync containers from Portainer

        Args:
            environment_id (int, optional): Environment ID to sync containers for.
                If not provided, syncs containers for all environments.
        """
        self.ensure_one()

        try:
            # Keep track of synced container IDs to mark missing ones as inactive
            synced_container_ids = []

            # Get environments to sync
            if environment_id:
                environments = self.environment_ids.filtered(lambda e: e.environment_id == environment_id)
            else:
                environments = self.environment_ids

            container_count = 0
            updated_count = 0
            created_count = 0

            # Sync containers for each environment
            for env in environments:
                endpoint_id = env.environment_id

                # Get all containers for this endpoint
                response = self._make_api_request(f'/api/endpoints/{endpoint_id}/docker/containers/json', 'GET',
                                                  params={'all': True})

                if response.status_code != 200:
                    _logger.warning(f"Failed to get containers for environment {env.name}: {response.text}")
                    continue

                containers = response.json()

                for container in containers:
                    container_id = container.get('Id')
                    container_name = container.get('Names', ['Unknown'])[0].lstrip('/')

                    # Check if container already exists in Odoo
                    existing_container = self.env['j_portainer.container'].search([
                        ('server_id', '=', self.id),
                        ('environment_id', '=', env.id),
                        ('container_id', '=', container_id)
                    ], limit=1)

                    # Get container details
                    details_response = self._make_api_request(
                        f'/api/endpoints/{endpoint_id}/docker/containers/{container_id}/json', 'GET')

                    details = details_response.json() if details_response.status_code == 200 else {}

                    # Get container state
                    state = details.get('State', {})
                    status = state.get('Status', 'unknown')

                    # Get container restart policy
                    restart_policy = 'no'  # Default to 'no' (Never)
                    host_config = details.get('HostConfig', {})
                    if host_config:
                        restart_policy_data = host_config.get('RestartPolicy', {})
                        if restart_policy_data:
                            restart_policy_name = restart_policy_data.get('Name', '')
                            if restart_policy_name:
                                restart_policy = restart_policy_name

                    # Determine if container is part of a stack
                    stack_id = False
                    container_labels = container.get('Labels', {})
                    if container_labels:
                        # Try multiple label patterns that Portainer might use
                        stack_name = (
                                container_labels.get('com.docker.compose.project') or
                                container_labels.get('com.docker.stack.namespace') or
                                container_labels.get('com.portainer.stack.name') or
                                container_labels.get('io.portainer.stack.name')
                        )

                        if stack_name:
                            # Try exact match first - use the Odoo environment record ID
                            stack = self.env['j_portainer.stack'].search([
                                ('server_id', '=', self.id),
                                ('environment_id', '=', env.id),
                                ('name', '=', stack_name)
                            ], limit=1)

                            # If no exact match, try case-insensitive search
                            if not stack:
                                stack = self.env['j_portainer.stack'].search([
                                    ('server_id', '=', self.id),
                                    ('environment_id', '=', env.id),
                                    ('name', 'ilike', stack_name)
                                ], limit=1)

                            if stack:
                                stack_id = stack.id
                                _logger.debug(
                                    f"Container {container_name} linked to stack {stack.name} (ID: {stack.id})")
                            else:
                                _logger.debug(
                                    f"No matching stack found for container {container_name} with stack name '{stack_name}'")

                    # Extract volume information from container details
                    volumes_data = []
                    mounts = details.get('Mounts', [])
                    if mounts:
                        volumes_data = mounts

                    # Extract runtime & resource configuration
                    host_config = details.get('HostConfig', {})

                    # Get memory limits - convert from bytes to MB
                    memory_reservation = host_config.get('MemoryReservation', 0)
                    if memory_reservation > 0:
                        memory_reservation = int(memory_reservation / (1024 * 1024))

                    memory_limit = host_config.get('Memory', 0)
                    if memory_limit > 0:
                        memory_limit = int(memory_limit / (1024 * 1024))

                    # Get CPU limit
                    nano_cpus = host_config.get('NanoCpus', 0)
                    cpu_limit = 0.0
                    if nano_cpus > 0:
                        cpu_limit = round(nano_cpus / 1000000000.0, 2)  # Convert from nano to full CPUs

                    # Get shared memory size
                    shm_size = 64  # Default value
                    if 'ShmSize' in host_config:
                        shm_size_bytes = host_config.get('ShmSize', 0)
                        if shm_size_bytes > 0:
                            shm_size = int(shm_size_bytes / (1024 * 1024))  # Convert from bytes to MB

                    # Process Linux capabilities
                    # Initialize with default values (False for all)
                    capabilities = {
                        'cap_audit_control': False,
                        'cap_audit_write': False,
                        'cap_block_suspend': False,
                        'cap_chown': False,
                        'cap_dac_override': False,
                        'cap_dac_read_search': False,
                        'cap_fowner': False,
                        'cap_fsetid': False,
                        'cap_ipc_lock': False,
                        'cap_ipc_owner': False,
                        'cap_kill': False,
                        'cap_lease': False,
                        'cap_linux_immutable': False,
                        'cap_mac_admin': False,
                        'cap_mac_override': False,
                        'cap_mknod': False,
                        'cap_net_admin': False,
                        'cap_net_bind_service': False,
                        'cap_net_broadcast': False,
                        'cap_net_raw': False,
                        'cap_setfcap': False,
                        'cap_setgid': False,
                        'cap_setpcap': False,
                        'cap_setuid': False,
                        'cap_syslog': False,
                        'cap_sys_admin': False,
                        'cap_sys_boot': False,
                        'cap_sys_chroot': False,
                        'cap_sys_module': False,
                        'cap_sys_nice': False,
                        'cap_sys_pacct': False,
                        'cap_sys_ptrace': False,
                        'cap_sys_rawio': False,
                        'cap_sys_resource': False,
                        'cap_sys_time': False,
                        'cap_sys_tty_config': False,
                        'cap_wake_alarm': False
                    }

                    # Extract capability information from HostConfig
                    cap_add = host_config.get('CapAdd', [])
                    if cap_add:
                        for cap in cap_add:
                            # Docker API returns capabilities with 'CAP_' prefix
                            if cap and isinstance(cap, str):
                                cap_lower = cap.lower().replace('cap_', '')
                                field_name = f'cap_{cap_lower}'
                                if field_name in capabilities:
                                    capabilities[field_name] = True

                    # Find or create image record for this container
                    image_record = False
                    image_id_value = container.get('ImageID', '')
                    if image_id_value:
                        image_record = self.env['j_portainer.image'].search([
                            ('server_id', '=', self.id),
                            ('environment_id', '=', env.id),
                            ('image_id', '=', image_id_value)
                        ], limit=1)

                    # Prepare data for create/update
                    container_data = {
                        'server_id': self.id,
                        'environment_id': env.id,  # Use the Many2one relation
                        'container_id': container_id,
                        'name': container_name,
                        'image_id': image_record.id if image_record else False,
                        'created': self._safe_parse_timestamp(container.get('Created', 0)),
                        'status': status,
                        'state': 'running' if state.get('Running', False) else 'stopped',
                        'restart_policy': restart_policy,
                        'ports': json.dumps(container.get('Ports', [])),
                        'labels': json.dumps(container.get('Labels', {})),
                        'details': json.dumps(details, indent=2) if details else '',
                        'volumes': json.dumps(volumes_data),
                        'stack_id': stack_id,

                        # Network port configuration
                        'publish_all_ports': host_config.get('PublishAllPorts', False),

                        # Runtime configuration
                        'privileged': host_config.get('Privileged', False),
                        'init_process': host_config.get('Init', False),
                        'shm_size': shm_size,

                        # Resource limits
                        'memory_reservation': memory_reservation,
                        'memory_limit': memory_limit,
                        'cpu_limit': cpu_limit,

                        # Image pull policy - not directly available from API, keep default
                        'always_pull_image': False,

                        # Linux Capabilities
                        'cap_audit_control': capabilities.get('cap_audit_control', False),
                        'cap_audit_write': capabilities.get('cap_audit_write', False),
                        'cap_block_suspend': capabilities.get('cap_block_suspend', False),
                        'cap_chown': capabilities.get('cap_chown', False),
                        'cap_dac_override': capabilities.get('cap_dac_override', False),
                        'cap_dac_read_search': capabilities.get('cap_dac_read_search', False),
                        'cap_fowner': capabilities.get('cap_fowner', False),
                        'cap_fsetid': capabilities.get('cap_fsetid', False),
                        'cap_ipc_lock': capabilities.get('cap_ipc_lock', False),
                        'cap_ipc_owner': capabilities.get('cap_ipc_owner', False),
                        'cap_kill': capabilities.get('cap_kill', False),
                        'cap_lease': capabilities.get('cap_lease', False),
                        'cap_linux_immutable': capabilities.get('cap_linux_immutable', False),
                        'cap_mac_admin': capabilities.get('cap_mac_admin', False),
                        'cap_mac_override': capabilities.get('cap_mac_override', False),
                        'cap_mknod': capabilities.get('cap_mknod', False),
                        'cap_net_admin': capabilities.get('cap_net_admin', False),
                        'cap_net_bind_service': capabilities.get('cap_net_bind_service', False),
                        'cap_net_broadcast': capabilities.get('cap_net_broadcast', False),
                        'cap_net_raw': capabilities.get('cap_net_raw', False),
                        'cap_setfcap': capabilities.get('cap_setfcap', False),
                        'cap_setgid': capabilities.get('cap_setgid', False),
                        'cap_setpcap': capabilities.get('cap_setpcap', False),
                        'cap_setuid': capabilities.get('cap_setuid', False),
                        'cap_syslog': capabilities.get('cap_syslog', False),
                        'cap_sys_admin': capabilities.get('cap_sys_admin', False),
                        'cap_sys_boot': capabilities.get('cap_sys_boot', False),
                        'cap_sys_chroot': capabilities.get('cap_sys_chroot', False),
                        'cap_sys_module': capabilities.get('cap_sys_module', False),
                        'cap_sys_nice': capabilities.get('cap_sys_nice', False),
                        'cap_sys_pacct': capabilities.get('cap_sys_pacct', False),
                        'cap_sys_ptrace': capabilities.get('cap_sys_ptrace', False),
                        'cap_sys_rawio': capabilities.get('cap_sys_rawio', False),
                        'cap_sys_resource': capabilities.get('cap_sys_resource', False),
                        'cap_sys_time': capabilities.get('cap_sys_time', False),
                        'cap_sys_tty_config': capabilities.get('cap_sys_tty_config', False),
                        'cap_wake_alarm': capabilities.get('cap_wake_alarm', False)
                    }

                    # Process container creation/update
                    if existing_container:
                        # Update existing container record
                        existing_container.write(container_data)
                        container_record = existing_container
                        updated_count += 1
                    else:
                        # Create new container record - mark as sync operation
                        container_record = self.env['j_portainer.container'].with_context(
                            sync_from_portainer=True).create(container_data)
                        created_count += 1

                    # Process container labels as separate records
                    # Smart sync labels using container's smart sync method
                    labels_dict = container.get('Labels', {})
                    container_record._smart_sync_labels(details)

                    # Smart sync volumes using container's smart sync method
                    container_record._smart_sync_volumes(details)

                    # Smart sync networks using container's smart sync method
                    container_record._smart_sync_networks(details)

                    # Smart sync environment variables using container's smart sync method
                    container_record._smart_sync_env_vars(details)

                    # Smart sync ports using container's smart sync method
                    container_record._smart_sync_ports(details)

                    synced_container_ids.append((endpoint_id, container_id))
                    container_count += 1

            # Clean up containers that no longer exist in Portainer
            # Get containers for this server (filtered by environment if specified)
            if environment_id:
                all_containers = self.env['j_portainer.container'].search([
                    ('server_id', '=', self.id),
                    ('environment_id.environment_id', '=', environment_id)
                ])
            else:
                all_containers = self.env['j_portainer.container'].search([
                    ('server_id', '=', self.id)
                ])

            # Filter containers that should be removed (not found in Portainer)
            containers_to_remove = all_containers.filtered(
                lambda c: (c.environment_id.environment_id, c.container_id) not in synced_container_ids
            )

            # Remove obsolete containers
            if containers_to_remove:
                removed_count = len(containers_to_remove)
                _logger.info(f"Removing {removed_count} obsolete containers from Odoo (already removed from Portainer)")
                containers_to_remove.unlink()
            else:
                removed_count = 0

            # Log the statistics
            _logger.info(
                f"Container sync complete: {container_count} total containers, {created_count} created, {updated_count} updated, {removed_count} removed")

            # Update container-specific last_sync
            now = fields.Datetime.now()
            containers = self.env['j_portainer.container'].search([
                ('server_id', '=', self.id)
            ])
            if containers:
                containers.write({'last_sync': now})

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Containers Synchronized'),
                    'message': _('%d containers found, %d created, %d updated, %d removed') %
                               (container_count, created_count, updated_count, removed_count),
                    'sticky': False,
                    'type': 'success',
                }
            }

        except Exception as e:
            _logger.error(f"Error syncing containers: {str(e)}")
            raise UserError(_("Error syncing containers: %s") % str(e))

    def sync_images(self, environment_id=None):
        """Sync images from Portainer

        Args:
            environment_id (int, optional): Environment ID to sync images for.
                If not provided, syncs images for all environments.
        """
        self.ensure_one()

        try:
            # Keep track of synced image IDs
            synced_image_ids = []

            # Get environments to sync
            if environment_id:
                environments = self.environment_ids.filtered(lambda e: e.environment_id == environment_id)
            else:
                environments = self.environment_ids

            image_count = 0
            updated_count = 0
            created_count = 0

            # Sync images for each environment
            for env in environments:
                endpoint_id = env.environment_id

                # Get all images for this endpoint
                # response = self._make_api_request(f'/api/docker/{endpoint_id}/images', 'GET')
                response = self._make_api_request(f'/api/endpoints/{endpoint_id}/docker/images/json', 'GET')
                print('response, ', response)
                if response.status_code != 200:
                    _logger.warning(f"Failed to get images for environment {env.name}: {response.text}")
                    continue

                images = response.json()
                print('images, ', images)

                for image in images:
                    image_id = image.get('Id')

                    # Get tags (repos)
                    repos = image.get('RepoTags', [])
                    repo_digests = image.get('RepoDigests', [])

                    # Get image details
                    details_response = self._make_api_request(
                        f'/api/endpoints/{endpoint_id}/docker/images/{image_id}/json', 'GET')

                    details = details_response.json() if details_response.status_code == 200 else {}

                    # Get containers to check if image is in use
                    containers_response = self._make_api_request(
                        f'/api/endpoints/{endpoint_id}/docker/containers/json', 'GET',
                        params={'all': True}  # Get all containers, including stopped ones
                    )

                    containers = containers_response.json() if containers_response.status_code == 200 else []

                    # Check if this image is used by any container
                    in_use = False
                    for container in containers:
                        container_image_id = container.get('ImageID', '')
                        # Docker sometimes uses short IDs in containers, so check if the image ID is contained
                        if image_id in container_image_id or container_image_id in image_id:
                            in_use = True
                            break

                    # Prepare base image data
                    # Use size values directly from the API response without any conversion
                    base_image_data = {
                        'server_id': self.id,
                        'environment_id': env.id,
                        'image_id': image_id,
                        'created': self._safe_parse_timestamp(image.get('Created', 0)),
                        'size': image.get('Size', 0),
                        'shared_size': image.get('SharedSize', 0),
                        'virtual_size': image.get('VirtualSize', 0),
                        'labels': json.dumps(image.get('Labels', {})),
                        'details': json.dumps(details, indent=2) if details else '',
                        'in_use': in_use,  # Add in_use field based on container usage
                    }

                    # Process images - only create one image record per Docker image ID
                    # Instead of creating multiple records for multiple tags
                    if repos and repos[0] != '<none>:<none>':
                        # Get the first tag as the primary one
                        primary_repo = repos[0]
                        if ':' in primary_repo:
                            primary_repository, primary_tag = primary_repo.split(':', 1)
                        else:
                            primary_repository, primary_tag = primary_repo, 'latest'

                        # Check if this image already exists in Odoo
                        existing_image = self.env['j_portainer.image'].search([
                            ('server_id', '=', self.id),
                            ('environment_id', '=', env.id),
                            ('image_id', '=', image_id)
                        ], limit=1)

                        # Prepare all tags information
                        tag_list = []
                        for repo in repos:
                            if ':' in repo:
                                repo_name, tag_name = repo.split(':', 1)
                            else:
                                repo_name, tag_name = repo, 'latest'

                            tag_list.append({
                                'repository': repo_name,
                                'tag': tag_name
                            })

                        # Get enhanced layer information using Docker Image History API
                        enhanced_layers = self._get_enhanced_image_layers(endpoint_id, image_id)

                        # Prepare image data with primary repository and tag plus all tags
                        image_data = dict(base_image_data)
                        image_data.update({
                            'repository': primary_repository,
                            'tag': primary_tag,
                            'all_tags': json.dumps(tag_list),
                            'enhanced_layers_data': json.dumps(enhanced_layers) if enhanced_layers else ''
                        })

                        if existing_image:
                            # Update existing image record
                            existing_image.write(image_data)
                            updated_count += 1
                        else:
                            # Create new image record
                            self.env['j_portainer.image'].with_context(sync_operation=True).create(image_data)
                            created_count += 1

                        image_count += 1
                        # Add all combinations to synced_image_ids to prevent cleanup of valid images
                        synced_image_ids.append((image_id, primary_repository, primary_tag))
                    elif repo_digests:
                        # Image has digests but no tags - extract repository from digest
                        # Format is usually repo@sha256:hash
                        for digest in repo_digests:
                            if '@' in digest:
                                repository = digest.split('@')[0]
                                tag = '<none>'  # Use '<none>' as tag for images with digest only to match Portainer

                                # Check if this image already exists in Odoo
                                existing_image = self.env['j_portainer.image'].search([
                                    ('server_id', '=', self.id),
                                    ('environment_id', '=', env.id),
                                    ('image_id', '=', image_id)
                                ], limit=1)

                                # Prepare tag information
                                tag_list = [{
                                    'repository': repository,
                                    'tag': tag
                                }]

                                # Get enhanced layer information using Docker Image History API
                                enhanced_layers = self._get_enhanced_image_layers(endpoint_id, image_id)

                                # Prepare specific image data with repository from digest
                                image_data = dict(base_image_data)
                                image_data.update({
                                    'repository': repository,
                                    'tag': tag,
                                    'all_tags': json.dumps(tag_list),
                                    'enhanced_layers_data': json.dumps(enhanced_layers) if enhanced_layers else ''
                                })

                                if existing_image:
                                    # Update existing image record
                                    existing_image.write(image_data)
                                    updated_count += 1
                                else:
                                    # Create new image record
                                    self.env['j_portainer.image'].with_context(sync_operation=True).create(image_data)
                                    created_count += 1

                                image_count += 1
                                synced_image_ids.append((image_id, repository, tag))
                                break  # Just use the first digest
                    else:
                        # Truly untagged image with no digests either
                        # Check if this untagged image already exists in Odoo
                        existing_image = self.env['j_portainer.image'].search([
                            ('server_id', '=', self.id),
                            ('environment_id', '=', env.id),
                            ('image_id', '=', image_id)
                        ], limit=1)

                        # Prepare tag information for untagged image
                        tag_list = [{
                            'repository': '<none>',
                            'tag': '<none>'
                        }]

                        # Prepare untagged image data
                        image_data = dict(base_image_data)
                        image_data.update({
                            'repository': '<none>',
                            'tag': '<none>',
                            'all_tags': json.dumps(tag_list)
                        })

                        if existing_image:
                            # Update existing image record
                            existing_image.write(image_data)
                            updated_count += 1
                        else:
                            # Create new image record
                            self.env['j_portainer.image'].with_context(sync_operation=True).create(image_data)
                            created_count += 1

                        image_count += 1
                        synced_image_ids.append((image_id, '<none>', '<none>'))

            # Clean up images that no longer exist in Portainer
            # Get images for this server (filtered by environment if specified)
            if environment_id:
                all_images = self.env['j_portainer.image'].search([
                    ('server_id', '=', self.id),
                    ('environment_id.environment_id', '=', environment_id)
                ])
            else:
                all_images = self.env['j_portainer.image'].search([
                    ('server_id', '=', self.id)
                ])

            # Collect all synced image IDs (without repository/tag)
            synced_ids = set()
            for image_tuple in synced_image_ids:
                synced_ids.add(image_tuple[0])  # Just extract the image_id part

            # Filter images that should be removed (not found in Portainer)
            images_to_remove = all_images.filtered(
                lambda img: img.image_id not in synced_ids
            )

            # Remove obsolete images
            if images_to_remove:
                removed_count = len(images_to_remove)
                _logger.info(f"Removing {removed_count} obsolete images from Odoo (already removed from Portainer)")
                images_to_remove.unlink()
            else:
                removed_count = 0

            # Log the statistics
            _logger.info(
                f"Image sync complete: {image_count} total images, {created_count} created, {updated_count} updated, {removed_count} removed")

            # Update image-specific last_sync
            now = fields.Datetime.now()
            images = self.env['j_portainer.image'].search([
                ('server_id', '=', self.id)
            ])
            if images:
                images.write({'last_sync': now})

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Images Synchronized'),
                    'message': _('%d images found, %d created, %d updated, %d removed') %
                               (image_count, created_count, updated_count, removed_count),
                    'sticky': False,
                    'type': 'success',
                }
            }

        except Exception as e:
            _logger.error(f"Error syncing images: {str(e)}")
            raise UserError(_("Error syncing images: %s") % str(e))

    def _get_enhanced_image_layers(self, environment_id, image_id):
        """
        Get enhanced layer information using Docker Image History API

        Args:
            environment_id (int): Environment ID
            image_id (str): Docker image ID

        Returns:
            list: Enhanced layer information with commands, sizes, and metadata
        """
        try:
            # Use the API client to get image history
            api = self.env['j_portainer.api']
            history_layers = api.get_image_history(self.id, environment_id, image_id)

            if history_layers:
                _logger.info(f"Retrieved {len(history_layers)} enhanced layers for image {image_id}")
                return history_layers
            else:
                _logger.warning(f"No enhanced layers retrieved for image {image_id}, keeping existing layer data")
                return None

        except Exception as e:
            _logger.error(f"Error getting enhanced layers for image {image_id}: {str(e)}")
            return None

    def sync_volumes(self, environment_id=None):
        """Sync volumes from Portainer

        Args:
            environment_id (int, optional): Environment ID to sync volumes for.
                If not provided, syncs volumes for all environments.
        """
        self.ensure_one()

        try:
            # Keep track of synced volumes
            synced_volume_names = []

            # Get environments to sync
            if environment_id:
                environments = self.environment_ids.filtered(lambda e: e.environment_id == environment_id)
            else:
                environments = self.environment_ids

            volume_count = 0
            updated_count = 0
            created_count = 0

            # Sync volumes for each environment
            for env in environments:
                endpoint_id = env.environment_id

                # Get all volumes for this endpoint
                response = self._make_api_request(f'/api/endpoints/{endpoint_id}/docker/volumes', 'GET')

                if response.status_code != 200:
                    _logger.warning(f"Failed to get volumes for environment {env.name}: {response.text}")
                    continue

                volumes_data = response.json()
                print('volumes_data .... ', volumes_data)
                volumes = volumes_data.get('Volumes', [])
                print('volumes .... ', volumes)

                for volume in volumes:
                    volume_name = volume.get('Name')

                    # Check if this volume already exists in Odoo
                    existing_volume = self.env['j_portainer.volume'].search([
                        ('server_id', '=', self.id),
                        ('environment_id.environment_id', '=', endpoint_id),
                        ('name', '=', volume_name)
                    ], limit=1)

                    # Get detailed info for this volume
                    details_response = self._make_api_request(
                        f'/api/endpoints/{endpoint_id}/docker/volumes/{volume_name}', 'GET')

                    details = details_response.json() if details_response.status_code == 200 else {}

                    # Get containers to check if volume is in use
                    containers_response = self._make_api_request(
                        f'/api/endpoints/{endpoint_id}/docker/containers/json', 'GET',
                        params={'all': True}  # Get all containers, including stopped ones
                    )

                    containers = containers_response.json() if containers_response.status_code == 200 else []

                    # Check if this volume is used by any container
                    in_use = False
                    connected_containers = []
                    for container in containers:
                        mounts = container.get('Mounts', [])
                        for mount in mounts:
                            # Check for volume mounts (named volumes)
                            if mount.get('Type') == 'volume' and mount.get('Name') == volume_name:
                                in_use = True
                                connected_containers.append({
                                    'container_name': container.get('Names', [''])[0].lstrip('/'),
                                    'container_id': container.get('Id', ''),
                                    'destination': mount.get('Destination', ''),
                                    'mode': mount.get('Mode', 'rw')
                                })
                            # Also check for bind mounts where source matches volume mountpoint
                            elif mount.get('Type') == 'bind' and mount.get('Source') == volume.get('Mountpoint'):
                                in_use = True
                                connected_containers.append({
                                    'container_name': container.get('Names', [''])[0].lstrip('/'),
                                    'container_id': container.get('Id', ''),
                                    'destination': mount.get('Destination', ''),
                                    'mode': mount.get('Mode', 'rw')
                                })
                        if in_use:
                            break

                    # Prepare volume data
                    volume_data = {
                        'server_id': self.id,
                        'environment_id': env.id,  # Use the Many2one relation
                        'name': volume_name,
                        'driver': volume.get('Driver', 'local'),
                        'created': self._safe_parse_timestamp(volume.get('CreatedAt', 0)),
                        'mountpoint': volume.get('Mountpoint', ''),
                        'scope': volume.get('Scope', 'local'),
                        'labels': json.dumps(volume.get('Labels', {})),
                        'details': json.dumps(details, indent=2) if details else '',
                        'in_use': in_use,  # Add in_use field based on container usage
                    }

                    if existing_volume:
                        # Update existing volume - don't update created date for existing records
                        existing_volume.write(volume_data)
                        updated_count += 1
                    else:
                        # Create new volume record - mark as sync operation
                        self.env['j_portainer.volume'].with_context(sync_from_portainer=True).create(volume_data)
                        created_count += 1

                    synced_volume_names.append((endpoint_id, volume_name))
                    volume_count += 1

            # Clean up volumes that no longer exist in Portainer
            # Get volumes for this server (filtered by environment if specified)
            if environment_id:
                all_volumes = self.env['j_portainer.volume'].search([
                    ('server_id', '=', self.id),
                    ('environment_id.environment_id', '=', environment_id)
                ])
            else:
                all_volumes = self.env['j_portainer.volume'].search([
                    ('server_id', '=', self.id)
                ])

            # Filter volumes that should be removed (not found in Portainer)
            volumes_to_remove = all_volumes.filtered(
                lambda v: (v.environment_id.environment_id, v.name) not in synced_volume_names
            )

            # Remove obsolete volumes
            if volumes_to_remove:
                removed_count = len(volumes_to_remove)
                _logger.info(f"Removing {removed_count} obsolete volumes from Odoo (already removed from Portainer)")
                volumes_to_remove.unlink()
            else:
                removed_count = 0

            # Log the statistics
            _logger.info(
                f"Volume sync complete: {volume_count} total volumes, {created_count} created, {updated_count} updated, {removed_count} removed")

            # Update volume-specific last_sync
            now = fields.Datetime.now()
            volumes = self.env['j_portainer.volume'].search([
                ('server_id', '=', self.id)
            ])
            if volumes:
                volumes.write({'last_sync': now})

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Volumes Synchronized'),
                    'message': _('%d volumes found, %d created, %d updated, %d removed') %
                               (volume_count, created_count, updated_count, removed_count),
                    'sticky': False,
                    'type': 'success',
                }
            }

        except Exception as e:
            _logger.error(f"Error syncing volumes: {str(e)}")
            raise UserError(_("Error syncing volumes: %s") % str(e))

    def sync_networks(self, environment_id=None):
        """Sync networks from Portainer

        Args:
            environment_id (int, optional): Environment ID to sync networks for.
                If not provided, syncs networks for all environments.
        """
        self.ensure_one()

        try:
            # Keep track of synced networks
            synced_network_ids = []

            # Get environments to sync
            if environment_id:
                environments = self.environment_ids.filtered(lambda e: e.environment_id == environment_id)
            else:
                environments = self.environment_ids

            network_count = 0
            updated_count = 0
            created_count = 0

            # Sync networks for each environment
            for env in environments:
                endpoint_id = env.environment_id

                # Get all networks for this endpoint
                response = self._make_api_request(f'/api/endpoints/{endpoint_id}/docker/networks', 'GET')

                if response.status_code != 200:
                    _logger.warning(f"Failed to get networks for environment {env.name}: {response.text}")
                    continue

                networks = response.json()

                for network in networks:
                    network_id = network.get('Id')

                    # Check if this network already exists in Odoo
                    existing_network = self.env['j_portainer.network'].search([
                        ('server_id', '=', self.id),
                        ('environment_id', '=', env.id),
                        ('network_id', '=', network_id)
                    ], limit=1)

                    # Get detailed info for this network
                    details_response = self._make_api_request(
                        f'/api/endpoints/{endpoint_id}/docker/networks/{network_id}', 'GET')

                    details = details_response.json() if details_response.status_code == 200 else {}

                    # Handle potential None values in nested dictionaries
                    ipam_data = network.get('IPAM') or {}
                    labels_data = network.get('Labels') or {}
                    containers_data = network.get('Containers') or {}
                    portainer_data = details.get('Portainer') or {}
                    resource_control = portainer_data.get('ResourceControl') or {}
                    options_data = details.get('Options') or {}

                    # Prepare network data
                    network_data = {
                        'server_id': self.id,
                        'environment_id': env.id,
                        'network_id': network_id,
                        'name': network.get('Name', ''),
                        'driver': network.get('Driver', 'bridge'),  # Use selection field with default value
                        'scope': network.get('Scope', 'local'),
                        'ipam': json.dumps(ipam_data),
                        'labels': json.dumps(labels_data),
                        'containers': json.dumps(containers_data),
                        'details': json.dumps(details, indent=2) if details else '',

                        # Get config options from details
                        'options': json.dumps(options_data),
                        # Additional boolean attributes from Portainer metadata
                        'public': resource_control.get('Public', True),
                        'administrators_only': resource_control.get('AdministratorsOnly', False),
                        'system': resource_control.get('System', False),

                        # Boolean attributes updated from details
                        'is_ipv6': details.get('EnableIPv6', False),
                        'internal': details.get('Internal', False),
                        'attachable': details.get('Attachable', False),
                        'isolated_network': details.get('Internal', False),  # Internal networks are isolated
                    }

                    # Create or update the main network record
                    if existing_network:
                        # Update existing network record
                        existing_network.write(network_data)
                        network_record = existing_network
                        updated_count += 1
                    else:
                        # Create new network record
                        network_record = self.env['j_portainer.network'].create(network_data)
                        created_count += 1

                    # Process IPv4 and IPv6 configuration from IPAM
                    ipam_data = network.get('IPAM', {}) or {}
                    ipam_config = ipam_data.get('Config', []) or []

                    # Process IPv4 and IPv6 configuration fields
                    for config in ipam_config:
                        subnet = config.get('Subnet', '')
                        gateway = config.get('Gateway', '')
                        ip_range = config.get('IPRange', '')

                        # Determine if this is IPv4 or IPv6 config
                        if subnet and ':' in subnet:  # IPv6 contains colons
                            network_record.write({
                                'ipv6_subnet': subnet,
                                'ipv6_gateway': gateway,
                                'ipv6_range': ip_range,
                            })

                            # Process excluded IPs if present
                            excluded_ips = config.get('ExcludedIPs', []) or []
                            if excluded_ips:
                                # Remove existing excluded IPs
                                existing_excluded = self.env['j_portainer.network.ipv6.excluded'].search([
                                    ('network_id', '=', network_record.id)
                                ])
                                if existing_excluded:
                                    existing_excluded.unlink()

                                # Create new excluded IPs
                                for ip in excluded_ips:
                                    self.env['j_portainer.network.ipv6.excluded'].create({
                                        'network_id': network_record.id,
                                        'ip_address': ip
                                    })
                        else:  # IPv4
                            network_record.write({
                                'ipv4_subnet': subnet,
                                'ipv4_gateway': gateway,
                                'ipv4_range': ip_range,
                            })

                            # Process excluded IPs if present
                            excluded_ips = config.get('ExcludedIPs', []) or []
                            if excluded_ips:
                                # Remove existing excluded IPs
                                existing_excluded = self.env['j_portainer.network.ipv4.excluded'].search([
                                    ('network_id', '=', network_record.id)
                                ])
                                if existing_excluded:
                                    existing_excluded.unlink()

                                # Create new excluded IPs
                                for ip in excluded_ips:
                                    self.env['j_portainer.network.ipv4.excluded'].create({
                                        'network_id': network_record.id,
                                        'ip_address': ip
                                    })

                    # Process driver options
                    options_data = details.get('Options', {}) or {}
                    if options_data:
                        # Remove existing driver options
                        existing_options = self.env['j_portainer.network.driver.option'].search([
                            ('network_id', '=', network_record.id)
                        ])
                        if existing_options:
                            existing_options.unlink()

                        # Create new driver options
                        for option_name, option_value in options_data.items():
                            self.env['j_portainer.network.driver.option'].create({
                                'network_id': network_record.id,
                                'name': option_name,
                                'value': str(option_value)  # Convert any non-string values to string
                            })

                    # Process network labels
                    labels_data = network.get('Labels', {}) or {}
                    if labels_data:
                        # Remove existing network labels
                        existing_labels = self.env['j_portainer.network.label'].search([
                            ('network_id', '=', network_record.id)
                        ])
                        if existing_labels:
                            existing_labels.unlink()

                        # Create new network labels
                        for label_name, label_value in labels_data.items():
                            self.env['j_portainer.network.label'].create({
                                'network_id': network_record.id,
                                'name': label_name,
                                'value': str(label_value)  # Convert any non-string values to string
                            })

                    synced_network_ids.append((env.id, network_id))
                    network_count += 1

            # Clean up networks that no longer exist in Portainer
            # Get networks for this server (filtered by environment if specified)
            if environment_id:
                all_networks = self.env['j_portainer.network'].search([
                    ('server_id', '=', self.id),
                    ('environment_id.environment_id', '=', environment_id)
                ])
            else:
                all_networks = self.env['j_portainer.network'].search([
                    ('server_id', '=', self.id)
                ])

            # Filter networks that should be removed (not found in Portainer)
            networks_to_remove = all_networks.filtered(
                lambda n: (n.environment_id.id, n.network_id) not in synced_network_ids
            )

            # Remove obsolete networks
            if networks_to_remove:
                removed_count = len(networks_to_remove)
                _logger.info(f"Removing {removed_count} obsolete networks from Odoo (already removed from Portainer)")
                networks_to_remove.unlink()
            else:
                removed_count = 0

            # Log the statistics
            _logger.info(
                f"Network sync complete: {network_count} total networks, {created_count} created, {updated_count} updated, {removed_count} removed")

            # Update network-specific last_sync
            now = fields.Datetime.now()
            networks = self.env['j_portainer.network'].search([
                ('server_id', '=', self.id)
            ])
            if networks:
                networks.write({'last_sync': now})

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Networks Synchronized'),
                    'message': _('%d networks found, %d created, %d updated, %d removed') %
                               (network_count, created_count, updated_count, removed_count),
                    'sticky': False,
                    'type': 'success',
                }
            }

        except Exception as e:
            _logger.error(f"Error syncing networks: {str(e)}")
            raise UserError(_("Error syncing networks: %s") % str(e))

    def _detect_environment_type(self, environment_id):
        """Detect if environment is Docker standalone or Docker Swarm"""
        try:
            # Get Docker info to check Swarm status
            response = self._make_api_request(f'/api/endpoints/{environment_id}/docker/info', 'GET')

            if response.status_code == 200:
                docker_info = response.json()

                # Check Swarm status
                swarm_info = docker_info.get('Swarm', {})
                node_id = swarm_info.get('NodeID', '')

                # If NodeID exists and is not empty, it's a Swarm environment
                if node_id and node_id.strip():
                    _logger.info(f"Environment {environment_id} detected as Docker Swarm")
                    return 'swarm'
                else:
                    _logger.info(f"Environment {environment_id} detected as Docker standalone")
                    return 'docker'
            else:
                _logger.warning(f"Failed to detect environment type for {environment_id}, defaulting to Docker")
                return 'docker'

        except Exception as e:
            _logger.error(f"Error detecting environment type for {environment_id}: {str(e)}")
            return 'docker'  # Default to Docker on error

    def sync_standard_templates(self):
        """Sync standard application templates from Portainer"""
        self.ensure_one()

        try:
            # Keep track of synced templates
            synced_template_ids = []

            # Detect environment types for filtering templates
            environment_types = {}
            for env in self.environment_ids:
                env_type = self._detect_environment_type(env.environment_id)
                environment_types[env.environment_id] = env_type

            # Get templates
            response = self._make_api_request('/api/templates', 'GET')

            if response.status_code != 200:
                raise UserError(_("Failed to get templates: %s") % response.text)

            # Parse the response - it could be a dict with 'templates' key or a direct array
            response_data = response.json()
            templates = []

            if isinstance(response_data, dict) and 'templates' in response_data:
                # New API format: {"version": "2", "templates": [...]}
                templates = response_data.get('templates', [])
                _logger.info(f"Using template list from 'templates' key, found {len(templates)} templates")
            elif isinstance(response_data, list):
                # Old API format: direct array of templates
                templates = response_data
                _logger.info(f"Using direct template list, found {len(templates)} templates")
            else:
                _logger.warning(f"Unexpected template response format: {type(response_data)}")
                if isinstance(response_data, dict):
                    _logger.warning(f"Template response keys: {list(response_data.keys())}")
                templates = []

            template_count = 0
            updated_count = 0
            created_count = 0

            for template in templates:
                # Skip if template is not a dictionary (sometimes API returns strings)
                if not isinstance(template, dict):
                    _logger.warning(f"Skipping non-dict template: {template}")
                    continue

                # Filter templates based on environment compatibility
                template_type = template.get('type', 1)

                # Check if any environment can use this template
                template_compatible = False
                for env_id, env_type in environment_types.items():
                    if env_type == 'swarm':
                        # Swarm environments support all template types (1, 2, 3)
                        template_compatible = True
                        break
                    elif env_type == 'docker' and template_type != 2:
                        # Docker environments support container (1) and compose stack (3) templates, but not Swarm stacks (2)
                        template_compatible = True
                        break

                if not template_compatible:
                    _logger.info(
                        f"Skipping template '{template.get('title', 'Unknown')}' (type {template_type}) - not compatible with current environments")
                    continue

                template_id = template.get('id')

                # Check if this template already exists in Odoo
                existing_template = False
                if template_id:
                    existing_template = self.env['j_portainer.template'].search([
                        ('server_id', '=', self.id),
                        ('template_id', '=', template_id)
                    ], limit=1)

                # Prepare template data
                template_data = {
                    'server_id': self.id,
                    'title': template.get('title', ''),
                    'description': template.get('description', ''),
                    'template_type': str(template.get('type', 1)),  # 1 = container, 2 = stack
                    'platform': template.get('platform', 'linux'),
                    'template_id': template_id,
                    'logo': template.get('logo', ''),
                    'registry': template.get('registry', ''),
                    'image': template.get('image', ''),
                    'repository': json.dumps(template.get('repository', {})) if isinstance(
                        template.get('repository', {}), dict) else '',
                    'categories': ','.join(template.get('categories', [])) if isinstance(template.get('categories', []),
                                                                                         list) else '',
                    'environment_variables': json.dumps(template.get('env', [])),
                    'volumes': json.dumps(template.get('volumes', [])),
                    'ports': json.dumps(template.get('ports', [])),
                    'note': template.get('note', ''),
                    'is_custom': False,
                    'details': json.dumps(template, indent=2),
                }

                if existing_template:
                    # Update existing template
                    existing_template.with_context(from_sync=True, skip_portainer_update=True).write(template_data)
                    updated_count += 1
                else:
                    # Create new template - skip Portainer creation since we're just syncing
                    template_data['skip_portainer_create'] = True
                    self.env['j_portainer.template'].with_context(from_sync=True, skip_portainer_create=True).create(
                        template_data)
                    created_count += 1

                if isinstance(template_id, (int, str)) and str(template_id).isdigit():
                    synced_template_ids.append(int(template_id))
                template_count += 1

            # Clean up templates that no longer exist in Portainer
            # Get all standard templates for this server
            all_templates = self.env['j_portainer.template'].search([
                ('server_id', '=', self.id),
                ('is_custom', '=', False)
            ])

            # Make sure all IDs are integers for proper comparison
            synced_ids = []
            for template_id in synced_template_ids:
                if isinstance(template_id, int) or (isinstance(template_id, str) and template_id.isdigit()):
                    synced_ids.append(int(template_id))

            # Templates to remove - those not in synced_template_ids
            # Handle template_id type conversion for comparison (some might be strings, some integers)
            templates_to_remove = all_templates.filtered(
                lambda t: (int(t.template_id) not in synced_ids) if t.template_id else True
            )

            # Remove obsolete templates
            if templates_to_remove:
                removed_count = len(templates_to_remove)
                _logger.info(f"Removing {removed_count} obsolete standard templates")
                templates_to_remove.unlink()
            else:
                removed_count = 0

            # Log the statistics
            _logger.info(
                f"Standard template sync complete: {template_count} total templates, {created_count} created, {updated_count} updated, {removed_count} removed")

            # Update template-specific last_sync
            now = fields.Datetime.now()
            templates = self.env['j_portainer.template'].search([
                ('server_id', '=', self.id)
            ])
            if templates:
                templates.write({'last_sync': now})

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Standard Templates Synchronized'),
                    'message': _('%d standard templates found, %d removed') % (template_count, removed_count),
                    'sticky': False,
                    'type': 'success',
                }
            }

        except Exception as e:
            _logger.error(f"Error syncing standard templates: {str(e)}")
            raise UserError(_("Error syncing standard templates: %s") % str(e))

    def sync_custom_templates(self):
        """Sync custom templates from Portainer"""
        self.ensure_one()

        try:
            # Keep track of synced custom template IDs
            synced_template_ids = []

            # For statistics
            template_count = 0
            updated_count = 0
            created_count = 0

            # Don't try to create templates in Portainer, just sync existing ones
            # We'll use skip_portainer_create flag for this

            # Get custom templates - try different API endpoints for different Portainer versions
            custom_templates = []
            custom_response = None

            # Use Portainer v2 API endpoint for custom templates
            try:
                custom_response = self._make_api_request('/api/custom_templates', 'GET')
                if custom_response.status_code == 200:
                    data = custom_response.json()
                    # Handle both array and object with templates array format
                    if isinstance(data, list):
                        custom_templates = data
                    elif isinstance(data, dict) and 'templates' in data:
                        custom_templates = data['templates']
                    else:
                        _logger.info(f"Custom templates data has unexpected format: {data}")
                else:
                    _logger.warning(
                        f"Failed to get custom templates from v2 API endpoint: {custom_response.status_code} - {custom_response.text}")
            except Exception as e:
                _logger.error(f"Error getting custom templates from v2 API: {str(e)}")

            # Process custom templates
            for template in custom_templates:
                # Skip if template is not a dictionary (sometimes API returns strings)
                if not isinstance(template, dict):
                    _logger.warning(f"Skipping non-dict custom template: {template}")
                    continue

                # Function to get field value regardless of capitalization
                def get_field_value(data, field_names, default=None):
                    """Get a field value from a dict using multiple possible field names in any capitalization"""
                    # Try exact matches first
                    for name in field_names:
                        if name in data:
                            return data[name]

                    # Try case-insensitive matches
                    lowercase_data = {k.lower(): v for k, v in data.items()}
                    for name in field_names:
                        if name.lower() in lowercase_data:
                            return lowercase_data[name.lower()]

                    return default

                # Handle different ID field names with case insensitivity
                template_id = get_field_value(template, ['id', 'Id', 'ID'])

                # Check if this custom template already exists in Odoo
                existing_template = False
                if template_id:
                    existing_template = self.env['j_portainer.customtemplate'].search([
                        ('server_id', '=', self.id),
                        ('template_id', '=', template_id)
                    ], limit=1)

                # Platform mapping function to handle numeric values
                def map_platform(platform_value):
                    """Map platform value to appropriate string value"""
                    if isinstance(platform_value, int) or (
                            isinstance(platform_value, str) and platform_value.isdigit()):
                        # Portainer sometimes uses numeric values for platform
                        platform_map = {
                            '1': 'linux',
                            '2': 'windows',
                            1: 'linux',
                            2: 'windows'
                        }
                        return platform_map.get(platform_value, 'linux')
                    elif isinstance(platform_value, str):
                        # If it's already a string like 'linux' or 'windows', use it directly
                        if platform_value.lower() in ['linux', 'windows']:
                            return platform_value.lower()
                    # Default fallback
                    return 'linux'

                # Get platform value with case-insensitive lookup
                platform_value = get_field_value(template, ['Platform', 'platform'])

                # Get environment ID from template or resource control
                portainer_environment_id = get_field_value(template, ['EndpointId', 'endpointId'], None)

                # Try to get environment ID from ResourceControl if available
                resource_control = get_field_value(template, ['ResourceControl', 'resourceControl'], None)
                if not portainer_environment_id and resource_control and isinstance(resource_control, dict):
                    portainer_environment_id = get_field_value(resource_control, ['EndpointId', 'endpointId'], None)

                # Ensure environment_id is numeric for comparison
                if isinstance(portainer_environment_id, str) and portainer_environment_id.isdigit():
                    portainer_environment_id = int(portainer_environment_id)

                # Map the Portainer environment ID to Odoo environment record ID
                environment_id_value = None
                if portainer_environment_id:
                    # Log all environments for debugging
                    env_data = [(e.id, e.environment_id, e.name) for e in self.environment_ids]
                    _logger.info(
                        f"Looking for environment ID {portainer_environment_id} in available environments: {env_data}")

                    # Find the matching environment record in Odoo based on Portainer's environment_id
                    matching_env = self.environment_ids.filtered(
                        lambda e: str(e.environment_id) == str(portainer_environment_id))
                    if matching_env:
                        environment_id_value = matching_env[0].id
                        _logger.info(
                            f"Mapped Portainer environment ID {portainer_environment_id} to Odoo environment record ID {environment_id_value}")
                    else:
                        _logger.warning(f"No matching environment found for Portainer ID {portainer_environment_id}")

                # If still no environment ID found, use first available environment as fallback
                if not environment_id_value and self.environment_ids:
                    environment_id_value = self.environment_ids[0].id
                    _logger.warning(
                        f"No environment ID found in template {template_id}, using first environment as fallback: {environment_id_value}")

                # Prepare custom template data with case-insensitive field extraction
                template_data = {
                    'server_id': self.id,
                    'environment_id': environment_id_value,  # Set environment ID (required field)
                    'title': get_field_value(template, ['Title', 'title'], ''),
                    'description': get_field_value(template, ['Description', 'description'], ''),
                    'template_type': str(get_field_value(template, ['Type', 'type'], 1)),
                    'platform': map_platform(platform_value),
                    'template_id': template_id,
                    'logo': get_field_value(template, ['Logo', 'logo'], ''),
                    'image': get_field_value(template, ['Image', 'image'], ''),
                    'repository': json.dumps(get_field_value(template, ['Repository', 'repository'], {})) if isinstance(
                        get_field_value(template, ['Repository', 'repository'], {}), dict) else '',
                    'categories': ','.join(get_field_value(template, ['Categories', 'categories'], [])) if isinstance(
                        get_field_value(template, ['Categories', 'categories'], []), list) else '',
                    'environment_variables': json.dumps(get_field_value(template, ['Env', 'env'], [])),
                    'volumes': json.dumps(get_field_value(template, ['Volumes', 'volumes'], [])),
                    'ports': json.dumps(get_field_value(template, ['Ports', 'ports'], [])),
                    'note': get_field_value(template, ['Note', 'note'], ''),
                    'is_custom': True,
                    'details': json.dumps(template, indent=2),
                    # Additional fields from Portainer with case-insensitive lookup
                    'project_path': get_field_value(template, ['ProjectPath', 'projectPath', 'projectpath'], ''),
                    'entry_point': get_field_value(template, ['EntryPoint', 'entryPoint', 'entrypoint'], ''),
                    'created_by_user_id': get_field_value(template,
                                                          ['CreatedByUserId', 'createdByUserId', 'createdbyuserid'], 0),
                    'registry_url': get_field_value(template, ['Registry', 'registry'], ''),
                }

                # Add Git repository information if available
                repo_url = get_field_value(template, ['repositoryURL', 'RepositoryURL'])
                if repo_url:
                    template_data['build_method'] = 'repository'
                    template_data['git_repository_url'] = repo_url
                    template_data['git_repository_reference'] = get_field_value(template, ['repositoryReferenceName',
                                                                                           'RepositoryReferenceName'],
                                                                                '')
                    template_data['git_compose_path'] = get_field_value(template,
                                                                        ['composeFilePath', 'ComposeFilePath'], '')
                    template_data['git_skip_tls'] = get_field_value(template, ['skipTLSVerify', 'SkipTLSVerify'], False)
                    template_data['git_authentication'] = get_field_value(template, ['repositoryAuthentication',
                                                                                     'RepositoryAuthentication'], False)
                # Check for compose file content in any of the possible field names
                compose_content = get_field_value(template, ['fileContent', 'FileContent', 'composeFileContent',
                                                             'ComposeFileContent'], '')

                # If no file content in the template data, try to get it from the file API endpoint
                if not compose_content and template_id:
                    try:
                        _logger.info(
                            f"No file content found in template data, fetching from file API endpoint for template ID: {template_id}")
                        file_response = self._make_api_request(f'/api/custom_templates/{template_id}/file', 'GET')

                        if file_response.status_code == 200:
                            file_data = file_response.json()
                            # Try different possible field names for the file content
                            for field_name in ['FileContent', 'StackFileContent', 'Content', 'stackFileContent']:
                                if field_name in file_data:
                                    compose_content = file_data[field_name]
                                    _logger.info(
                                        f"Retrieved file content (field: {field_name}) from API for template '{template_data['title']}'. Content length: {len(compose_content)} chars")
                                    break

                            # If we still don't have content, log the entire response
                            if not compose_content:
                                _logger.warning(f"File content not found in response: {file_data}")
                        else:
                            _logger.warning(
                                f"Failed to get file content for custom template {template_id}: {file_response.status_code} - {file_response.text}")
                    except Exception as e:
                        _logger.error(f"Error fetching file content for template {template_id}: {str(e)}")

                if compose_content:
                    _logger.info(
                        f"Using file content for template '{template_data['title']}' (ID: {template_id}). Content length: {len(compose_content)} chars")
                    template_data['build_method'] = 'editor'  # Web editor method
                    template_data['fileContent'] = compose_content  # Use fileContent field instead of compose_file
                    template_data['compose_file'] = compose_content  # Keep compose_file for backward compatibility

                if existing_template:
                    # Update existing custom template
                    existing_template.with_context(from_sync=True, skip_portainer_update=True).write(template_data)
                    updated_count += 1
                else:
                    # Create new custom template - skip Portainer creation since we're just syncing
                    template_data['skip_portainer_create'] = True

                    # Double check that environment_id is set and is a valid ID
                    if not template_data.get('environment_id'):
                        # Find the first valid environment as fallback
                        if self.environment_ids:
                            template_data['environment_id'] = self.environment_ids[0].id
                            _logger.warning(
                                f"No environment ID found for template {template_id}, using first environment {self.environment_ids[0].id} as fallback")
                        else:
                            _logger.error(f"Cannot create custom template {template_id}: No environment found")
                            continue

                    try:
                        self.env['j_portainer.customtemplate'].with_context(from_sync=True,
                                                                            skip_portainer_create=True).create(
                            template_data)
                        created_count += 1
                    except Exception as e:
                        _logger.error(f"Error creating custom template: {str(e)}")
                        # Continue with next template instead of failing the entire sync

                if isinstance(template_id, (int, str)) and str(template_id).isdigit():
                    synced_template_ids.append(int(template_id))
                template_count += 1

            # Clean up custom templates that no longer exist in Portainer
            # Get all custom templates for this server
            all_custom_templates = self.env['j_portainer.customtemplate'].search([
                ('server_id', '=', self.id)
            ])

            # Make sure all IDs are integers for proper comparison
            synced_ids = []
            for template_id in synced_template_ids:
                if isinstance(template_id, int) or (isinstance(template_id, str) and template_id.isdigit()):
                    synced_ids.append(int(template_id))

            # Templates to remove - those not in synced_template_ids
            # Handle template_id type conversion for comparison (some might be strings, some integers)
            templates_to_remove = all_custom_templates.filtered(
                lambda t: (int(t.template_id) not in synced_ids) if t.template_id else True
            )

            # Remove obsolete custom templates
            if templates_to_remove:
                removed_count = len(templates_to_remove)
                _logger.info(f"Removing {removed_count} obsolete custom templates")
                templates_to_remove.unlink()
            else:
                removed_count = 0

            # Log the statistics
            _logger.info(
                f"Custom template sync complete: {template_count} total custom templates, {created_count} created, {updated_count} updated, {removed_count} removed")

            # Update custom template-specific last_sync
            now = fields.Datetime.now()
            custom_templates = self.env['j_portainer.customtemplate'].search([
                ('server_id', '=', self.id)
            ])
            if custom_templates:
                custom_templates.write({'last_sync': now})

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Custom Templates Synchronized'),
                    'message': _('%d custom templates found, %d removed') % (template_count, removed_count),
                    'sticky': False,
                    'type': 'success',
                }
            }

        except Exception as e:
            _logger.error(f"Error syncing custom templates: {str(e)}")
            raise UserError(_("Error syncing custom templates: %s") % str(e))

    def push_custom_templates_to_portainer(self):
        """Push custom templates from Odoo to Portainer"""
        self.ensure_one()

        try:
            # Get all custom templates for this server that are not marked to skip creation
            custom_templates = self.env['j_portainer.customtemplate'].search([
                ('server_id', '=', self.id),
                ('skip_portainer_create', '=', False)
            ])

            if not custom_templates:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('No Templates to Push'),
                        'message': _('No custom templates found to push to Portainer'),
                        'sticky': False,
                        'type': 'info',
                    }
                }

            success_count = 0
            error_count = 0

            for template in custom_templates:
                try:
                    _logger.info(f"Pushing template '{template.title}' to Portainer")

                    # Check if this template already exists in Portainer
                    if template.template_id:
                        # Update existing template
                        _logger.info(f"Updating existing template with ID: {template.template_id}")
                        response = template._sync_to_portainer(method='put')
                    else:
                        # Create a new template
                        _logger.info("Creating new template in Portainer")
                        response = template.action_create_in_portainer()

                    # Check if successful
                    if response and isinstance(response, dict) and (
                            'Id' in response or 'id' in response or 'success' in response):
                        success_count += 1

                        # Log new template ID if one was assigned
                        template_id = response.get('Id') or response.get('id')
                        if template_id and not template.template_id:
                            _logger.info(f"Template '{template.title}' created with ID: {template_id}")
                    else:
                        error_count += 1
                        _logger.warning(f"Failed to push template '{template.title}': {response}")
                except Exception as e:
                    error_count += 1
                    _logger.error(f"Error pushing template '{template.title}': {str(e)}")

            # Update custom template-specific last_sync
            now = fields.Datetime.now()
            custom_templates = self.env['j_portainer.customtemplate'].search([
                ('server_id', '=', self.id)
            ])
            if custom_templates:
                custom_templates.write({'last_sync': now})

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Templates Pushed to Portainer'),
                    'message': _('%d templates successfully pushed, %d errors') % (success_count, error_count),
                    'sticky': False,
                    'type': 'success' if error_count == 0 else 'warning',
                }
            }
        except Exception as e:
            _logger.error(f"Error pushing templates to Portainer: {str(e)}")
            raise UserError(_("Error pushing templates to Portainer: %s") % str(e))

    def _fetch_missing_template_file_content(self):
        """Private implementation to fetch missing file content for templates that have a template_id but no file content"""
        self.ensure_one()

        try:
            # Find all custom templates for this server with a template_id but no file content
            templates_without_content = self.env['j_portainer.customtemplate'].search([
                ('server_id', '=', self.id),
                ('template_id', '!=', False),
                '|',
                ('fileContent', '=', False),
                ('fileContent', '=', '')
            ])

            if not templates_without_content:
                _logger.info("No templates missing file content")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('No Missing Content'),
                        'message': _('No templates with missing file content found.'),
                        'sticky': False,
                        'type': 'info',
                    }
                }

            _logger.info(f"Found {len(templates_without_content)} templates missing file content")
            success_count = 0
            total_count = len(templates_without_content)

            for template in templates_without_content:
                try:
                    _logger.info(f"Fetching file content for template '{template.title}' (ID: {template.template_id})")
                    file_response = self._make_api_request(f'/api/custom_templates/{template.template_id}/file', 'GET')

                    if file_response.status_code == 200:
                        file_data = file_response.json()
                        compose_content = None

                        # Try different possible field names for the file content
                        for field_name in ['FileContent', 'StackFileContent', 'Content', 'stackFileContent']:
                            if field_name in file_data:
                                compose_content = file_data[field_name]
                                _logger.info(
                                    f"Retrieved file content (field: {field_name}) for template '{template.title}'. Content length: {len(compose_content)} chars")
                                break

                        if compose_content:
                            template.write({
                                'fileContent': compose_content,
                                'compose_file': compose_content,
                                'build_method': 'editor'
                            })
                            success_count += 1
                        else:
                            _logger.warning(
                                f"No file content found in response for template {template.template_id}: {file_data}")
                    else:
                        _logger.warning(
                            f"Failed to get file content for template {template.template_id}: {file_response.status_code} - {file_response.text}")
                except Exception as e:
                    _logger.error(f"Error fetching file content for template {template.template_id}: {str(e)}")

            _logger.info(f"Successfully fetched file content for {success_count} of {total_count} templates")

            # Return notification for the user
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('File Content Updated'),
                    'message': _('Fetched file content for %d of %d templates') % (success_count, total_count),
                    'sticky': False,
                    'type': 'success',
                }
            }

        except Exception as e:
            _logger.error(f"Error fetching template file content: {str(e)}")
            raise UserError(_("Error fetching template file content: %s") % str(e))

    def sync_templates(self):
        """Sync all templates (standard and custom) from Portainer"""
        self.ensure_one()

        try:
            # First sync standard templates
            self.sync_standard_templates()

            # Then sync custom templates
            self.sync_custom_templates()

            # Fetch missing file content for any templates that still need it
            self._fetch_missing_template_file_content()  # Use private method to avoid duplicate notifications

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('All Templates Synchronized'),
                    'message': _('Both standard and custom templates have been synchronized.'),
                    'sticky': False,
                    'type': 'success',
                }
            }

        except Exception as e:
            _logger.error(f"Error syncing templates: {str(e)}")
            raise UserError(_("Error syncing templates: %s") % str(e))

    def sync_stacks(self, environment_id=None):
        """Sync stacks from Portainer

        Args:
            environment_id (int, optional): Environment ID to sync stacks for.
                If not provided, syncs stacks for all environments.
        """
        self.ensure_one()

        try:
            # Keep track of synced stacks
            synced_stack_ids = []

            # Get environments to sync
            if environment_id:
                environments = self.environment_ids.filtered(lambda e: e.environment_id == environment_id)
            else:
                environments = self.environment_ids

            stack_count = 0
            updated_count = 0
            created_count = 0

            # Sync stacks for each environment
            for env in environments:
                endpoint_id = env.environment_id

                # Get all stacks
                response = self._make_api_request('/api/stacks', 'GET')

                if response.status_code != 200:
                    _logger.warning(f"Failed to get stacks: {response.text}")
                    continue

                stacks = response.json()

                # Filter stacks for this environment
                env_stacks = [s for s in stacks if s.get('EndpointId') == endpoint_id]

                for stack in env_stacks:
                    stack_id = stack.get('Id')

                    # Check if this stack already exists in Odoo
                    existing_stack = self.env['j_portainer.stack'].search([
                        ('server_id', '=', self.id),
                        ('environment_id', '=', env.id),
                        ('stack_id', '=', stack_id)
                    ], limit=1)

                    # Get stack file content if available
                    file_content = ''
                    file_response = self._make_api_request(f'/api/stacks/{stack_id}/file', 'GET')
                    if file_response.status_code == 200:
                        file_data = file_response.json()
                        file_content = file_data.get('StackFileContent', '')

                    # Prepare stack data
                    stack_data = {
                        'server_id': self.id,
                        'environment_id': env.id,
                        'stack_id': stack_id,
                        'name': stack.get('Name', ''),
                        'type': str(stack.get('Type', 1)),
                        'status': str(stack.get('Status', 0)),
                        'update_date': self._parse_date_value(stack.get('UpdateDate')),
                        'file_content': file_content,
                        'content': file_content,  # Populate both content fields
                        'details': json.dumps(stack, indent=2),
                    }

                    if existing_stack:
                        # Update existing stack - don't update creation date for existing records
                        existing_stack.write(stack_data)
                        updated_count += 1
                    else:
                        # Create new stack record - set creation date
                        stack_data['creation_date'] = self._parse_date_value(
                            stack.get('CreationDate')) or datetime.now()
                        self.env['j_portainer.stack'].create(stack_data)
                        created_count += 1

                    synced_stack_ids.append((env.id, stack_id))
                    stack_count += 1

            # Clean up stacks that no longer exist in Portainer
            # Get stacks for this server (filtered by environment if specified)
            if environment_id:
                all_stacks = self.env['j_portainer.stack'].search([
                    ('server_id', '=', self.id),
                    ('environment_id.environment_id', '=', environment_id)
                ])
            else:
                all_stacks = self.env['j_portainer.stack'].search([
                    ('server_id', '=', self.id)
                ])

            # Filter stacks that should be removed (not found in Portainer)
            stacks_to_remove = all_stacks.filtered(
                lambda s: (s.environment_id.id, s.stack_id) not in synced_stack_ids
            )

            # Remove obsolete stacks
            if stacks_to_remove:
                removed_count = len(stacks_to_remove)
                _logger.info(f"Removing {removed_count} obsolete stacks from Odoo (already removed from Portainer)")
                stacks_to_remove.unlink()
            else:
                removed_count = 0

            # Log the statistics
            _logger.info(
                f"Stack sync complete: {stack_count} total stacks, {created_count} created, {updated_count} updated, {removed_count} removed")

            # Update stack-specific last_sync
            now = fields.Datetime.now()
            stacks = self.env['j_portainer.stack'].search([
                ('server_id', '=', self.id)
            ])
            if stacks:
                stacks.write({'last_sync': now})

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Stacks Synchronized'),
                    'message': _('%d stacks found, %d created, %d updated, %d removed') %
                               (stack_count, created_count, updated_count, removed_count),
                    'sticky': False,
                    'type': 'success',
                }
            }

        except Exception as e:
            _logger.error(f"Error syncing stacks: {str(e)}")
            raise UserError(_("Error syncing stacks: %s") % str(e))

    def action_view_api_logs(self):
        """Open the API logs for this server"""
        self.ensure_one()
        return {
            'name': _('API Logs'),
            'view_mode': 'tree,form',
            'res_model': 'j_portainer.api_log',
            'domain': [('server_id', '=', self.id)],
            'type': 'ir.actions.act_window',
            'context': {'default_server_id': self.id}
        }

    def sync_all(self):
        """Sync all resources from Portainer"""
        self.ensure_one()

        try:
            # Sync environments first
            self.sync_environments()

            # Sync all other resources
            self.sync_images()
            self.sync_volumes()
            self.sync_networks()
            self.sync_standard_templates()
            self.sync_custom_templates()

            # Fetch missing file content for any templates
            self._fetch_missing_template_file_content()  # Use private method to avoid duplicate notifications

            self.sync_stacks()
            self.sync_containers()
            self.write({'last_sync': fields.Datetime.now()})

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Synchronization Complete'),
                    'message': _('All Portainer resources have been synchronized.'),
                    'sticky': False,
                    'type': 'success',
                }
            }

        except Exception as e:
            _logger.error(f"Error during full sync: {str(e)}")
            raise UserError(_("Error during full sync: %s") % str(e))

    def _create_default_backup_schedule(self):
        """Create default backup schedule for new server"""
        self.ensure_one()

        # Check if backup schedule already exists
        existing_schedule = self.env['j_portainer.backup.schedule'].search([
            ('server_id', '=', self.id)
        ], limit=1)

        if not existing_schedule:
            # Create default backup schedule
            self.env['j_portainer.backup.schedule'].create({
                'server_id': self.id,
                'backup_password': 'default_password_change_me',
                'schedule_days': 1,
                'active': True,
            })
            _logger.info(f"Created default backup schedule for server: {self.name}")

    @api.model
    def _execute_scheduled_backups(self):
        """Cron method to execute scheduled backups for all servers"""
        _logger.info("Starting scheduled backup execution check")

        try:
            # Get all active backup schedules
            schedules = self.env['j_portainer.backup.schedule'].search([
                ('active', '=', True)
            ])

            executed_count = 0
            total_schedules = len(schedules)

            _logger.info(f"Found {total_schedules} active backup schedules to check")

            for schedule in schedules:
                try:
                    if schedule.is_backup_due():
                        _logger.info(f"Executing scheduled backup for server: {schedule.server_id.name}")
                        success = schedule.execute_backup()
                        if success:
                            executed_count += 1
                        else:
                            _logger.warning(f"Scheduled backup failed for server: {schedule.server_id.name}")
                    else:
                        _logger.debug(f"Backup not due for server: {schedule.server_id.name}")
                except Exception as e:
                    _logger.error(f"Error executing scheduled backup for server {schedule.server_id.name}: {str(e)}")
                    continue

            _logger.info(
                f"Scheduled backup execution complete: {executed_count} backups executed out of {total_schedules} schedules checked")

            # Optional: Clean up old backup files for servers with successful backups
            for schedule in schedules:
                try:
                    # Clean up old backups, keeping only 10 most recent per server
                    self.env['j_portainer.backup.history'].cleanup_old_backups(
                        schedule.server_id.id, keep_count=10
                    )
                except Exception as e:
                    _logger.warning(f"Error during backup cleanup for server {schedule.server_id.name}: {str(e)}")

        except Exception as e:
            _logger.error(f"Error in scheduled backup execution: {str(e)}")

    def get_backup_schedule(self):
        """Get backup schedule for this server (creates one if it doesn't exist)"""
        self.ensure_one()

        schedule = self.env['j_portainer.backup.schedule'].search([
            ('server_id', '=', self.id)
        ], limit=1)

        if not schedule:
            # Create default backup schedule if none exists
            schedule = self.env['j_portainer.backup.schedule'].create({
                'server_id': self.id,
                'backup_password': 'default_password_change_me',
                'schedule_days': 1,
                'active': True,
            })

        return schedule

    def action_execute_scheduled_backup_now(self):
        """Execute scheduled backup manually from server form"""
        self.ensure_one()

        schedule = self.get_backup_schedule()
        if not schedule:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No Backup Schedule'),
                    'message': _('No backup schedule found for this server.'),
                    'sticky': False,
                    'type': 'warning',
                }
            }

        return schedule.action_execute_backup_now()
