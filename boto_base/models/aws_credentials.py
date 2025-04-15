# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
#
# Copyright (C) 2023 JAAH

import json
import logging
import boto3
import botocore
from datetime import timedelta
from odoo import api, fields, models, _, tools
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)

AWS_SERVICES = [
    ('apigateway', 'API Gateway'),
    ('athena', 'Athena'),
    ('autoscaling', 'Auto Scaling'),
    ('cloudformation', 'CloudFormation'),
    ('cloudfront', 'CloudFront'),
    ('cloudsearch', 'CloudSearch'),
    ('cloudtrail', 'CloudTrail'),
    ('cloudwatch', 'CloudWatch'),
    ('cognito', 'Cognito'),
    ('comprehend', 'Comprehend'),
    ('config', 'Config'),
    ('datapipeline', 'Data Pipeline'),
    ('dynamodb', 'DynamoDB'),
    ('ec2', 'EC2'),
    ('ecr', 'ECR'),
    ('ecs', 'ECS'),
    ('efs', 'EFS'),
    ('eks', 'EKS'),
    ('elasticache', 'ElastiCache'),
    ('elasticbeanstalk', 'Elastic Beanstalk'),
    ('elastictranscoder', 'Elastic Transcoder'),
    ('elb', 'ELB'),
    ('elbv2', 'ELBv2'),
    ('emr', 'EMR'),
    ('es', 'Elasticsearch'),
    ('firehose', 'Firehose'),
    ('glacier', 'Glacier'),
    ('glue', 'Glue'),
    ('iam', 'IAM'),
    ('kinesis', 'Kinesis'),
    ('kms', 'KMS'),
    ('lambda', 'Lambda'),
    ('lex-runtime', 'Lex Runtime'),
    ('lightsail', 'Lightsail'),
    ('logs', 'CloudWatch Logs'),
    ('machinelearning', 'Machine Learning'),
    ('mediaconvert', 'MediaConvert'),
    ('mq', 'MQ'),
    ('organizations', 'Organizations'),
    ('polly', 'Polly'),
    ('rds', 'RDS'),
    ('redshift', 'Redshift'),
    ('rekognition', 'Rekognition'),
    ('route53', 'Route 53'),
    ('route53domains', 'Route 53 Domains'),
    ('s3', 'S3'),
    ('sagemaker', 'SageMaker'),
    ('secretsmanager', 'Secrets Manager'),
    ('ses', 'SES'),
    ('shield', 'Shield'),
    ('sms', 'SMS'),
    ('snowball', 'Snowball'),
    ('sns', 'SNS'),
    ('sqs', 'SQS'),
    ('ssm', 'SSM'),
    ('storagegateway', 'Storage Gateway'),
    ('sts', 'STS'),
    ('textract', 'Textract'),
    ('transcribe', 'Transcribe'),
    ('transfer', 'Transfer'),
    ('translate', 'Translate'),
    ('waf', 'WAF'),
    ('workdocs', 'WorkDocs'),
    ('workmail', 'WorkMail'),
    ('workspaces', 'WorkSpaces'),
    ('xray', 'X-Ray'),
]

class AWSCredentials(models.Model):
    _name = 'aws.credentials'
    _description = 'AWS Credentials'
    _rec_name = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    
    name = fields.Char(string='Credentials Name', required=True, index=True, tracking=True)
    aws_access_key_id = fields.Char(string='AWS Access Key ID', required=True, tracking=True)
    aws_secret_access_key = fields.Char(string='AWS Secret Access Key', required=True)
    aws_session_token = fields.Char(string='AWS Session Token', 
                                   help='Temporary session token, if using temporary credentials')
    aws_default_region = fields.Char(string='Default AWS Region', default='us-east-1', tracking=True,
                                     help='Default region for these credentials')
    aws_profile = fields.Char(string='AWS Profile', 
                             help='Optional AWS CLI profile name to use instead of access keys')
    
    endpoint_url = fields.Char(string='Custom Endpoint URL', 
                              help='Optional custom endpoint URL for AWS services')
    
    description = fields.Text(string='Description')
    is_default = fields.Boolean(string='Default Credentials', default=False, tracking=True,
                                help='Set these credentials as the default for new configurations')
    active = fields.Boolean(default=True, string='Active', tracking=True)
    
    last_validation = fields.Datetime(string='Last Validated', readonly=True)
    is_valid = fields.Boolean(string='Valid', readonly=True, tracking=True)
    validation_message = fields.Text(string='Validation Message', readonly=True)
    validation_services = fields.Text(string='Validated Services', readonly=True, 
                                     help='JSON list of AWS services successfully validated')
    
    allowed_service_ids = fields.Many2many('aws.service', string='Allowed Services',
                                          help='If set, restricts these credentials to specific AWS services')
    iam_user = fields.Char(string='IAM User', compute='_compute_iam_info', store=True)
    iam_user_id = fields.Char(string='IAM User ID', compute='_compute_iam_info', store=True)
    account_id = fields.Char(string='AWS Account ID', compute='_compute_iam_info', store=True)
    
    credential_type = fields.Selection([
        ('access_key', 'Access Key'),
        ('profile', 'AWS CLI Profile'),
        ('environment', 'Environment Variables'),
        ('instance_profile', 'EC2 Instance Profile'),
    ], string='Credential Type', default='access_key', required=True, tracking=True)
    
    # For keeping track of usage
    last_used = fields.Datetime(string='Last Used')
    usage_count = fields.Integer(string='Usage Count', default=0)
    
    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'Credentials name must be unique!')
    ]
    
    @api.model
    def _name_search(self, name, args=None, operator='ilike', limit=100, name_get_uid=None):
        args = args or []
        if operator == 'ilike' and not (name or '').strip():
            domain = []
        else:
            domain = ['|', ('name', operator, name), ('aws_default_region', operator, name)]
        return self._search(domain + args, limit=limit, access_rights_uid=name_get_uid)
    
    @api.depends('aws_access_key_id', 'is_valid')
    def _compute_iam_info(self):
        for record in self:
            if not record.is_valid or record.credential_type != 'access_key':
                record.iam_user = False
                record.iam_user_id = False
                record.account_id = False
                continue
                
            try:
                session = record.get_boto3_session()
                sts_client = session.client('sts')
                identity = sts_client.get_caller_identity()
                
                # Extract user name from ARN if possible
                arn = identity.get('Arn', '')
                if ':user/' in arn:
                    record.iam_user = arn.split(':user/')[1]
                else:
                    record.iam_user = arn
                    
                record.iam_user_id = identity.get('UserId', '')
                record.account_id = identity.get('Account', '')
            except Exception as e:
                _logger.warning('Could not retrieve IAM info: %s', str(e))
                record.iam_user = False
                record.iam_user_id = False
                record.account_id = False
    
    @api.constrains('is_default')
    def _check_default_credentials(self):
        # Ensure only one default credentials set exists
        if self.is_default:
            other_defaults = self.search([
                ('is_default', '=', True),
                ('id', '!=', self.id)
            ])
            if other_defaults:
                other_defaults.write({'is_default': False})
                
    @api.constrains('credential_type', 'aws_access_key_id', 'aws_secret_access_key', 'aws_profile')
    def _check_credential_requirements(self):
        for record in self:
            if record.credential_type == 'access_key':
                if not record.aws_access_key_id or not record.aws_secret_access_key:
                    raise ValidationError(_("Access Key ID and Secret Access Key are required for Access Key credentials."))
            elif record.credential_type == 'profile':
                if not record.aws_profile:
                    raise ValidationError(_("Profile name is required for AWS CLI Profile credentials."))
    
    def get_boto3_session(self, region_name=None, service_name=None):
        """
        Create and return a boto3 session using these credentials.
        
        Args:
            region_name: Optional region name to override the default
            service_name: Optional service name to validate access for
            
        Returns:
            boto3.Session object
        """
        self.ensure_one()
        
        # Use specified region or the credential's default
        region = region_name or self.aws_default_region
        
        # Track usage
        self.write({
            'last_used': fields.Datetime.now(),
            'usage_count': self.usage_count + 1,
        })
        
        # Create session based on credential type
        session_args = {'region_name': region}
        
        if self.credential_type == 'access_key':
            session_args['aws_access_key_id'] = self.aws_access_key_id
            session_args['aws_secret_access_key'] = self.aws_secret_access_key
            if self.aws_session_token:
                session_args['aws_session_token'] = self.aws_session_token
        elif self.credential_type == 'profile':
            session_args['profile_name'] = self.aws_profile
        elif self.credential_type == 'environment':
            # Uses environment variables; no args needed
            pass
        elif self.credential_type == 'instance_profile':
            # Uses EC2 instance profile; no args needed
            pass
            
        try:
            return boto3.Session(**session_args)
        except Exception as e:
            _logger.error('Failed to create boto3 session: %s', str(e))
            raise UserError(_('Failed to create AWS session: %s') % str(e))
    
    def get_client(self, service_name, region_name=None, endpoint_url=None):
        """
        Get a boto3 client for the specified AWS service.
        
        Args:
            service_name: AWS service name (e.g., 's3', 'ec2', 'route53')
            region_name: Optional region name to override the default
            endpoint_url: Optional endpoint URL to override the default
            
        Returns:
            boto3.client object
        """
        self.ensure_one()
        
        # Check if service is allowed
        if self.allowed_service_ids:
            allowed_services = self.allowed_service_ids.mapped('code')
            if service_name not in allowed_services:
                raise UserError(_('These credentials are not allowed to access the %s service.') % service_name)
                
        try:
            session = self.get_boto3_session(region_name=region_name)
            
            # Use custom endpoint if provided
            client_args = {}
            if endpoint_url or self.endpoint_url:
                client_args['endpoint_url'] = endpoint_url or self.endpoint_url
                
            # If connecting to S3, use path-style for compatibility
            if service_name == 's3':
                client_args['config'] = botocore.config.Config(s3={'addressing_style': 'path'})
                
            return session.client(service_name, **client_args)
        except Exception as e:
            _logger.error('Failed to create %s client: %s', service_name, str(e))
            raise UserError(_('Failed to create %s client: %s') % (service_name, str(e)))
    
    def get_resource(self, service_name, region_name=None, endpoint_url=None):
        """
        Get a boto3 resource for the specified AWS service.
        
        Args:
            service_name: AWS service name (e.g., 's3', 'ec2', 'dynamodb')
            region_name: Optional region name to override the default
            endpoint_url: Optional endpoint URL to override the default
            
        Returns:
            boto3.resource object
        """
        self.ensure_one()
        
        # Check if service is allowed
        if self.allowed_service_ids:
            allowed_services = self.allowed_service_ids.mapped('code')
            if service_name not in allowed_services:
                raise UserError(_('These credentials are not allowed to access the %s service.') % service_name)
                
        try:
            session = self.get_boto3_session(region_name=region_name)
            
            # Use custom endpoint if provided
            resource_args = {}
            if endpoint_url or self.endpoint_url:
                resource_args['endpoint_url'] = endpoint_url or self.endpoint_url
                
            return session.resource(service_name, **resource_args)
        except Exception as e:
            _logger.error('Failed to create %s resource: %s', service_name, str(e))
            raise UserError(_('Failed to create %s resource: %s') % (service_name, str(e)))
    
    def test_credentials(self, services=None):
        """
        Test if the AWS credentials are valid by making API calls to specified services.
        Updates validation fields with the result.
        
        Args:
            services: Optional list of service names to test, defaults to ['ec2', 'sts']
        """
        self.ensure_one()
        
        if not services:
            services = ['ec2', 'sts']
            
        successful_services = []
        errors = []
        
        try:
            # Create a session
            session = self.get_boto3_session()
            
            # Test STS for basic identity information
            if 'sts' in services:
                try:
                    sts_client = session.client('sts')
                    identity = sts_client.get_caller_identity()
                    successful_services.append('sts')
                    
                    # Update identity info
                    arn = identity.get('Arn', '')
                    if ':user/' in arn:
                        self.iam_user = arn.split(':user/')[1]
                    else:
                        self.iam_user = arn
                        
                    self.iam_user_id = identity.get('UserId', '')
                    self.account_id = identity.get('Account', '')
                except Exception as e:
                    errors.append(f"STS: {str(e)}")
            
            # Test additional services
            for service in services:
                if service == 'sts' and 'sts' in successful_services:
                    continue
                    
                try:
                    # Make a simple API call for each service
                    client = session.client(service)
                    
                    if service == 'ec2':
                        client.describe_regions()
                    elif service == 's3':
                        client.list_buckets()
                    elif service == 'route53':
                        client.list_hosted_zones(MaxItems='1')
                    elif service == 'iam':
                        client.list_users(MaxItems=1)
                    elif service == 'rds':
                        client.describe_db_instances(MaxRecords=1)
                    else:
                        # Generic test for other services (not all will work with this)
                        client._service_model.operation_names[:1]
                        
                    successful_services.append(service)
                except Exception as e:
                    errors.append(f"{service}: {str(e)}")
            
            # Determine overall validation status
            is_valid = len(successful_services) > 0
            
            # Update validation fields
            self.write({
                'last_validation': fields.Datetime.now(),
                'is_valid': is_valid,
                'validation_message': '\n'.join(errors) if errors else _("Credentials validated successfully"),
                'validation_services': json.dumps(successful_services),
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success') if is_valid else _('Warning'),
                    'message': _('%d service(s) validated successfully. %d service(s) failed.') % 
                              (len(successful_services), len(errors)),
                    'sticky': bool(errors),
                    'type': 'success' if is_valid else 'warning',
                    'next': {
                        'type': 'ir.actions.act_window',
                        'res_model': 'aws.credentials',
                        'res_id': self.id,
                        'view_mode': 'form',
                    } if errors else None,
                }
            }
            
        except Exception as e:
            # Update validation fields with error
            self.write({
                'last_validation': fields.Datetime.now(),
                'is_valid': False,
                'validation_message': str(e),
                'validation_services': json.dumps([]),
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
    
    def deep_test_credentials(self):
        """Test credentials against multiple AWS services"""
        return self.test_credentials(services=['sts', 'ec2', 's3', 'iam', 'route53', 'rds', 'cloudwatch'])
    
    @api.model
    def get_default_credentials(self):
        """
        Get the default AWS credentials.
        
        Returns:
            aws.credentials record marked as default or None
        """
        return self.search([('is_default', '=', True), ('active', '=', True)], limit=1)
        
    @api.model
    def get_credentials_for_service(self, service_name, region_name=None):
        """
        Get appropriate credentials for a specific AWS service.
        
        Args:
            service_name: AWS service name (e.g., 's3', 'ec2', 'route53')
            region_name: Optional region name to filter by
            
        Returns:
            aws.credentials record or None
        """
        domain = [('active', '=', True), ('is_valid', '=', True)]
        
        # Filter by region if specified
        if region_name:
            domain.append(('aws_default_region', '=', region_name))
            
        # Find credentials specifically allowed for this service
        credentials = self.search(domain)
        
        # Filter for those that can access this service
        service_credentials = credentials.filtered(
            lambda c: not c.allowed_service_ids or 
                     service_name in c.allowed_service_ids.mapped('code')
        )
        
        # Prefer default credentials if available
        default_credentials = service_credentials.filtered(lambda c: c.is_default)
        if default_credentials:
            return default_credentials[0]
            
        # Otherwise return the first valid credentials
        return service_credentials[0] if service_credentials else None
        
    def execute_with_error_handling(self, method, *args, **kwargs):
        """
        Execute an AWS API method with standardized error handling.
        
        Args:
            method: Callable method from a boto3 client
            *args: Positional arguments for the method
            **kwargs: Keyword arguments for the method
            
        Returns:
            Result of the API call
            
        Raises:
            UserError: For common AWS exceptions with user-friendly messages
        """
        try:
            return method(*args, **kwargs)
        except botocore.exceptions.ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_msg = e.response.get('Error', {}).get('Message', str(e))
            
            # Map common AWS errors to user-friendly messages
            user_friendly_errors = {
                'AccessDenied': _('Access denied. Check IAM permissions for this operation.'),
                'InvalidAccessKeyId': _('Invalid Access Key ID. Please check your credentials.'),
                'SignatureDoesNotMatch': _('Invalid Secret Access Key. Please check your credentials.'),
                'AuthFailure': _('Authentication failed. Please check your credentials.'),
                'ValidationError': _('Validation error: %s') % error_msg,
                'ResourceNotFoundException': _('Resource not found: %s') % error_msg,
                'InvalidParameterValue': _('Invalid parameter: %s') % error_msg,
                'MissingParameter': _('Missing required parameter: %s') % error_msg,
            }
            
            message = user_friendly_errors.get(error_code, f"{error_code}: {error_msg}")
            _logger.error("AWS API Error: %s", message)
            raise UserError(message)
        except botocore.exceptions.NoCredentialsError:
            raise UserError(_('No AWS credentials found or credentials are invalid.'))
        except botocore.exceptions.EndpointConnectionError as e:
            raise UserError(_('Could not connect to AWS: %s') % str(e))
        except Exception as e:
            _logger.exception("AWS API Error")
            raise UserError(_('AWS API Error: %s') % str(e))


class AWSService(models.Model):
    _name = 'aws.service'
    _description = 'AWS Service'
    _order = 'name'
    
    name = fields.Char(string='Service Name', required=True)
    code = fields.Char(string='Service Code', required=True)
    description = fields.Text(string='Description')
    active = fields.Boolean(default=True)
    
    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'Service code must be unique!')
    ]
    
    @api.model
    def _init_aws_services(self):
        """Initialize the AWS services list"""
        for code, name in AWS_SERVICES:
            existing = self.search([('code', '=', code)])
            if not existing:
                self.create({
                    'name': name,
                    'code': code,
                    'active': True,
                })
                
    @api.model
    def get_service_by_code(self, code):
        """Get a service record by its code"""
        return self.search([('code', '=', code), ('active', '=', True)], limit=1)