# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
#
# Copyright (C) 2023 JAAH

import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

class Route53HealthCheck(models.Model):
    """
    Represents an AWS Route 53 health check.
    """
    _name = 'aws.route53.health.check'
    _description = 'Route 53 Health Check'
    _inherit = ['aws.service.implementation.mixin', 'aws.service.logger']
    
    name = fields.Char(string='Health Check Name', required=True)
    health_check_id = fields.Char(string='Health Check ID', readonly=True)
    
    health_check_type = fields.Selection([
        ('HTTP', 'HTTP'),
        ('HTTPS', 'HTTPS'),
        ('HTTP_STR_MATCH', 'HTTP String Match'),
        ('HTTPS_STR_MATCH', 'HTTPS String Match'),
        ('TCP', 'TCP'),
        ('CALCULATED', 'Calculated'),
        ('CLOUDWATCH_METRIC', 'CloudWatch Metric'),
        ('RECOVERY_CONTROL', 'Route 53 Recovery Control')
    ], string='Type', required=True, default='HTTP')
    
    endpoint_url = fields.Char(string='Endpoint URL', help='Full URL for HTTP/HTTPS checks')
    endpoint_ip = fields.Char(string='IP Address', help='IP address for TCP checks')
    endpoint_port = fields.Integer(string='Port', help='Port for TCP checks')
    endpoint_path = fields.Char(string='Path', help='Path for HTTP/HTTPS checks')
    
    search_string = fields.Char(string='Search String', help='String to search for in the response')
    invert_search = fields.Boolean(string='Invert Search', default=False, 
                                  help='If true, the health check passes only if the string does NOT appear in the response')
    
    # Monitoring
    interval_seconds = fields.Integer(string='Interval (seconds)', default=30, 
                                     help='How often Route 53 sends requests to the endpoint')
    failure_threshold = fields.Integer(string='Failure Threshold', default=3, 
                                      help='Number of consecutive failed checks before marking unhealthy')
    enable_sni = fields.Boolean(string='Enable SNI', default=True, 
                               help='Server Name Indication for HTTPS checks')
    alarm_low_samples = fields.Integer(string='Alarm Low Samples', default=3, 
                                      help='For CloudWatch Metric checks')
    alarm_high_samples = fields.Integer(string='Alarm High Samples', default=3, 
                                       help='For CloudWatch Metric checks')
    
    # Status
    active = fields.Boolean(default=True)
    status = fields.Selection([
        ('healthy', 'Healthy'),
        ('unhealthy', 'Unhealthy'),
        ('unknown', 'Unknown')
    ], string='Current Status', default='unknown', readonly=True)
    last_check = fields.Datetime(string='Last Check', readonly=True)
    last_status_message = fields.Text(string='Last Status Message', readonly=True)
    
    sync_status = fields.Selection([
        ('not_synced', 'Not Synced'),
        ('syncing', 'Syncing'),
        ('synced', 'Synced'),
        ('error', 'Error')
    ], string='Sync Status', default='not_synced')
    last_sync = fields.Datetime(string='Last Sync')
    sync_message = fields.Text(string='Sync Message')
    
    @api.model
    def create(self, vals):
        """
        Create a new health check both in Odoo and AWS Route 53.
        """
        # Create locally first
        health_check = super(Route53HealthCheck, self).create(vals)
        
        # Don't create in AWS if sync is disabled or for data import
        if self.env.context.get('import_file') or self.env.context.get('no_aws_sync'):
            return health_check
        
        # Create in AWS
        try:
            health_check._create_health_check_in_aws()
        except Exception as e:
            health_check.write({
                'sync_status': 'error',
                'sync_message': str(e)
            })
            _logger.error("Failed to create Route 53 health check: %s", str(e))
            
        return health_check
    
    def write(self, vals):
        """
        Update health check both in Odoo and AWS Route 53.
        """
        result = super(Route53HealthCheck, self).write(vals)
        
        # Don't update in AWS if sync is disabled or for data import
        if self.env.context.get('import_file') or self.env.context.get('no_aws_sync'):
            return result
        
        # Check if relevant fields were changed
        config_fields = [
            'name', 'health_check_type', 'endpoint_url', 'endpoint_ip', 'endpoint_port',
            'endpoint_path', 'search_string', 'invert_search', 'interval_seconds',
            'failure_threshold', 'enable_sni', 'alarm_low_samples', 'alarm_high_samples'
        ]
        
        if any(field in vals for field in config_fields):
            for health_check in self:
                if health_check.health_check_id:
                    try:
                        health_check._update_health_check_in_aws()
                    except Exception as e:
                        health_check.write({
                            'sync_status': 'error',
                            'sync_message': str(e)
                        })
                        _logger.error("Failed to update Route 53 health check: %s", str(e))
                else:
                    try:
                        health_check._create_health_check_in_aws()
                    except Exception as e:
                        health_check.write({
                            'sync_status': 'error',
                            'sync_message': str(e)
                        })
                        _logger.error("Failed to create Route 53 health check: %s", str(e))
        
        return result
    
    def unlink(self):
        """
        Delete health check from AWS Route 53 before deleting from Odoo.
        """
        if not self.env.context.get('no_aws_sync'):
            for health_check in self:
                if health_check.health_check_id:
                    try:
                        health_check._delete_health_check_from_aws()
                    except Exception as e:
                        raise UserError(_("Cannot delete health check from AWS: %s") % str(e))
        
        return super(Route53HealthCheck, self).unlink()
    
    def _create_health_check_in_aws(self):
        """
        Create the health check in AWS Route 53.
        """
        self.ensure_one()
        
        # Get Route 53 client
        route53 = self.get_service_client('route53')
        
        # Prepare health check configuration
        health_check_config = {
            'Type': self.health_check_type,
            'RequestInterval': self.interval_seconds,
            'FailureThreshold': self.failure_threshold,
        }
        
        # Configure based on type
        if self.health_check_type in ['HTTP', 'HTTPS', 'HTTP_STR_MATCH', 'HTTPS_STR_MATCH']:
            if not self.endpoint_url:
                raise ValidationError(_("Endpoint URL is required for HTTP/HTTPS health checks."))
                
            health_check_config.update({
                'FullyQualifiedDomainName': self.endpoint_url,
                'ResourcePath': self.endpoint_path or '/',
                'Port': self.endpoint_port or (443 if 'HTTPS' in self.health_check_type else 80),
            })
            
            if self.health_check_type in ['HTTP_STR_MATCH', 'HTTPS_STR_MATCH']:
                if not self.search_string:
                    raise ValidationError(_("Search string is required for string match health checks."))
                
                health_check_config.update({
                    'SearchString': self.search_string,
                    'InvertHealthCheck': self.invert_search,
                })
                
            if 'HTTPS' in self.health_check_type:
                health_check_config['EnableSNI'] = self.enable_sni
                
        elif self.health_check_type == 'TCP':
            if not self.endpoint_ip or not self.endpoint_port:
                raise ValidationError(_("IP address and port are required for TCP health checks."))
                
            health_check_config.update({
                'IPAddress': self.endpoint_ip,
                'Port': self.endpoint_port,
            })
        
        # Create the health check
        success, result = self.aws_operation_with_logging(
            service_name='route53',
            operation='create_health_check',
            with_result=True,
            CallerReference=f"{self._name}-{self.id}-{fields.Datetime.now()}",
            HealthCheckConfig=health_check_config
        )
        
        if not success:
            raise UserError(_("Failed to create health check: %s") % result)
            
        # Update local record with AWS data
        health_check_id = result.get('HealthCheck', {}).get('Id')
        
        self.write({
            'health_check_id': health_check_id,
            'sync_status': 'synced',
            'last_sync': fields.Datetime.now(),
            'sync_message': _("Health check created successfully")
        })
        
        # Set tags for the health check
        try:
            self.aws_operation_with_logging(
                service_name='route53',
                operation='change_tags_for_resource',
                ResourceType='healthcheck',
                ResourceId=health_check_id,
                AddTags=[
                    {'Key': 'Name', 'Value': self.name},
                    {'Key': 'ManagedBy', 'Value': 'Odoo'},
                ]
            )
        except Exception as e:
            _logger.warning("Failed to add tags to health check: %s", str(e))
    
    def _update_health_check_in_aws(self):
        """
        Update the health check in AWS Route 53.
        """
        self.ensure_one()
        
        if not self.health_check_id:
            return self._create_health_check_in_aws()
            
        # Get Route 53 client
        route53 = self.get_service_client('route53')
        
        # Get current health check config
        success, result = self.aws_operation_with_logging(
            service_name='route53',
            operation='get_health_check',
            with_result=True,
            HealthCheckId=self.health_check_id
        )
        
        if not success:
            raise UserError(_("Failed to get health check: %s") % result)
            
        current_config = result.get('HealthCheck', {}).get('HealthCheckConfig', {})
        
        # Prepare new health check configuration
        health_check_config = {
            'FailureThreshold': self.failure_threshold,
        }
        
        # Configure based on type
        if self.health_check_type in ['HTTP', 'HTTPS', 'HTTP_STR_MATCH', 'HTTPS_STR_MATCH']:
            if not self.endpoint_url:
                raise ValidationError(_("Endpoint URL is required for HTTP/HTTPS health checks."))
                
            health_check_config.update({
                'FullyQualifiedDomainName': self.endpoint_url,
                'ResourcePath': self.endpoint_path or '/',
                'Port': self.endpoint_port or (443 if 'HTTPS' in self.health_check_type else 80),
            })
            
            if self.health_check_type in ['HTTP_STR_MATCH', 'HTTPS_STR_MATCH']:
                if not self.search_string:
                    raise ValidationError(_("Search string is required for string match health checks."))
                
                health_check_config.update({
                    'SearchString': self.search_string,
                    'InvertHealthCheck': self.invert_search,
                })
                
            if 'HTTPS' in self.health_check_type:
                health_check_config['EnableSNI'] = self.enable_sni
                
        elif self.health_check_type == 'TCP':
            if not self.endpoint_ip or not self.endpoint_port:
                raise ValidationError(_("IP address and port are required for TCP health checks."))
                
            health_check_config.update({
                'IPAddress': self.endpoint_ip,
                'Port': self.endpoint_port,
            })
        
        # Update the health check
        success, result = self.aws_operation_with_logging(
            service_name='route53',
            operation='update_health_check',
            with_result=True,
            HealthCheckId=self.health_check_id,
            **health_check_config
        )
        
        if not success:
            raise UserError(_("Failed to update health check: %s") % result)
            
        # Update local record with sync status
        self.write({
            'sync_status': 'synced',
            'last_sync': fields.Datetime.now(),
            'sync_message': _("Health check updated successfully")
        })
        
        # Update tags
        try:
            self.aws_operation_with_logging(
                service_name='route53',
                operation='change_tags_for_resource',
                ResourceType='healthcheck',
                ResourceId=self.health_check_id,
                AddTags=[
                    {'Key': 'Name', 'Value': self.name},
                ]
            )
        except Exception as e:
            _logger.warning("Failed to update tags for health check: %s", str(e))
    
    def _delete_health_check_from_aws(self):
        """
        Delete the health check from AWS Route 53.
        """
        self.ensure_one()
        
        if not self.health_check_id:
            return
            
        # Get Route 53 client
        route53 = self.get_service_client('route53')
        
        # Delete the health check
        success, result = self.aws_operation_with_logging(
            service_name='route53',
            operation='delete_health_check',
            with_result=True,
            HealthCheckId=self.health_check_id
        )
        
        if not success:
            raise UserError(_("Failed to delete health check: %s") % result)
    
    def refresh_status(self):
        """
        Refresh the health check status from AWS.
        """
        self.ensure_one()
        
        if not self.health_check_id:
            return
            
        # Get Route 53 client
        route53 = self.get_service_client('route53')
        
        try:
            # Get health check status
            success, result = self.aws_operation_with_logging(
                service_name='route53',
                operation='get_health_check_status',
                with_result=True,
                HealthCheckId=self.health_check_id
            )
            
            if not success:
                raise UserError(_("Failed to get health check status: %s") % result)
                
            health_check_observations = result.get('HealthCheckObservations', [])
            
            # Determine overall status
            status = 'unknown'
            status_message = ''
            
            if health_check_observations:
                # Count statuses
                healthy_count = sum(1 for obs in health_check_observations if obs.get('StatusReport', {}).get('Status') == 'Success')
                total_count = len(health_check_observations)
                
                if healthy_count == total_count:
                    status = 'healthy'
                    status_message = _("All endpoints are healthy")
                elif healthy_count == 0:
                    status = 'unhealthy'
                    status_message = _("All endpoints are unhealthy")
                else:
                    status = 'unhealthy'
                    status_message = _("%s of %s endpoints are healthy") % (healthy_count, total_count)
                
                # Add detailed status messages
                details = []
                for obs in health_check_observations:
                    status_report = obs.get('StatusReport', {})
                    region = obs.get('Region', 'Unknown')
                    obs_status = status_report.get('Status', 'Unknown')
                    obs_message = status_report.get('StatusReport', '')
                    details.append(f"{region}: {obs_status} - {obs_message}")
                
                if details:
                    status_message += "\n\n" + "\n".join(details)
            
            # Update local record with status
            self.write({
                'status': status,
                'last_check': fields.Datetime.now(),
                'last_status_message': status_message
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _("Health check status refreshed"),
                    'sticky': False,
                    'type': 'success',
                }
            }
            
        except Exception as e:
            self.write({
                'status': 'unknown',
                'last_check': fields.Datetime.now(),
                'last_status_message': str(e)
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': str(e),
                    'sticky': True,
                    'type': 'danger',
                }
            }
    
    @api.model
    def refresh_all_health_checks(self):
        """
        Refresh all active health checks.
        """
        health_checks = self.search([('active', '=', True), ('health_check_id', '!=', False)])
        
        for health_check in health_checks:
            try:
                health_check.refresh_status()
            except Exception as e:
                _logger.error("Failed to refresh health check %s: %s", health_check.name, str(e))
                
        return True
    
    @api.model
    def import_health_checks_from_aws(self, aws_credentials_id=None, region_name=None):
        """
        Import all health checks from AWS Route 53.
        
        Args:
            aws_credentials_id: Optional AWS credentials ID
            region_name: Optional AWS region name
        """
        # Get Route 53 client
        route53 = self.get_aws_client('route53', aws_credentials_id=aws_credentials_id, region_name=region_name)
        
        try:
            # Get all health checks from AWS
            response = route53.list_health_checks()
            health_checks = response.get('HealthChecks', [])
            
            # Create context to avoid creating health checks in AWS again
            ctx = dict(self.env.context, no_aws_sync=True)
            
            # Process health checks
            for hc in health_checks:
                health_check_id = hc.get('Id')
                config = hc.get('HealthCheckConfig', {})
                
                # Get tags
                tags_response = route53.list_tags_for_resource(
                    ResourceType='healthcheck',
                    ResourceId=health_check_id
                )
                tags = tags_response.get('ResourceTagSet', {}).get('Tags', [])
                name = next((tag.get('Value') for tag in tags if tag.get('Key') == 'Name'), f"Health Check {health_check_id}")
                
                # Check if health check already exists
                existing = self.search([('health_check_id', '=', health_check_id)])
                
                # Extract config values
                health_check_type = config.get('Type')
                endpoint_url = config.get('FullyQualifiedDomainName', '')
                endpoint_ip = config.get('IPAddress', '')
                endpoint_port = config.get('Port', 0)
                endpoint_path = config.get('ResourcePath', '/')
                search_string = config.get('SearchString', '')
                invert_search = config.get('InvertHealthCheck', False)
                interval_seconds = config.get('RequestInterval', 30)
                failure_threshold = config.get('FailureThreshold', 3)
                enable_sni = config.get('EnableSNI', True)
                
                vals = {
                    'name': name,
                    'health_check_id': health_check_id,
                    'health_check_type': health_check_type,
                    'endpoint_url': endpoint_url,
                    'endpoint_ip': endpoint_ip,
                    'endpoint_port': endpoint_port,
                    'endpoint_path': endpoint_path,
                    'search_string': search_string,
                    'invert_search': invert_search,
                    'interval_seconds': interval_seconds,
                    'failure_threshold': failure_threshold,
                    'enable_sni': enable_sni,
                    'sync_status': 'synced',
                    'last_sync': fields.Datetime.now(),
                }
                
                if existing:
                    # Update existing health check
                    existing.with_context(ctx).write(vals)
                else:
                    # Create new health check
                    self.with_context(ctx).create(vals)
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _("Successfully imported %s health checks") % len(health_checks),
                    'sticky': False,
                    'type': 'success',
                }
            }
            
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': str(e),
                    'sticky': True,
                    'type': 'danger',
                }
            }