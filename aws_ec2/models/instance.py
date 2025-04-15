# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
#
# Copyright (C) 2023 JAAH

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import json
import time
import logging

_logger = logging.getLogger(__name__)

class EC2Instance(models.Model):
    """
    Represents an AWS EC2 instance.
    """
    _name = 'aws.ec2.instance'
    _description = 'EC2 Instance'
    _inherit = ['aws.service.implementation.mixin', 'aws.service.logger']
    _rec_name = 'name'
    _order = 'name'

    # Instance Identifiers
    name = fields.Char(string='Name', required=True, index=True,
                      help='Name of the EC2 instance (tag:Name).')
    instance_id = fields.Char(string='Instance ID', readonly=True, index=True,
                             help='The unique ID of the EC2 instance (e.g. i-0123456789abcdef0).')
    
    # Instance Details
    instance_type = fields.Char(string='Instance Type', 
                               help='The instance type (e.g. t2.micro, m5.large).')
    image_id = fields.Char(string='AMI ID',
                          help='The Amazon Machine Image ID used for this instance.')
    key_pair_id = fields.Many2one('aws.ec2.key.pair', string='Key Pair',
                                 help='The key pair used for SSH access to this instance.')
    
    # Network Configuration
    vpc_id = fields.Char(string='VPC ID',
                        help='The VPC in which this instance is launched.')
    subnet_id = fields.Char(string='Subnet ID',
                           help='The subnet in which this instance is launched.')
    public_ip = fields.Char(string='Public IP', readonly=True,
                           help='The public IP address assigned to this instance.')
    private_ip = fields.Char(string='Private IP', readonly=True,
                            help='The private IP address assigned to this instance.')
    public_dns = fields.Char(string='Public DNS', readonly=True,
                            help='The public DNS name assigned to this instance.')
    private_dns = fields.Char(string='Private DNS', readonly=True,
                             help='The private DNS name assigned to this instance.')
    
    # Security
    security_group_ids = fields.Many2many('aws.ec2.security.group', string='Security Groups',
                                         help='Security groups associated with this instance.')
    
    # Status
    state = fields.Selection([
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('shutting-down', 'Shutting Down'),
        ('terminated', 'Terminated'),
        ('stopping', 'Stopping'),
        ('stopped', 'Stopped')
    ], string='State', readonly=True, default='pending',
    help='Current state of the instance.')
    
    # Monitoring
    monitoring_enabled = fields.Boolean(string='Monitoring Enabled', default=False,
                                       help='Whether detailed monitoring is enabled.')
    last_status_check = fields.Datetime(string='Last Status Check', readonly=True,
                                       help='Last time the instance status was checked.')
    system_status = fields.Selection([
        ('ok', 'OK'),
        ('impaired', 'Impaired'),
        ('insufficient-data', 'Insufficient Data'),
        ('not-applicable', 'Not Applicable'),
        ('initializing', 'Initializing')
    ], string='System Status', readonly=True, default='not-applicable',
    help='Status of Amazon EC2 systems required to use this instance.')
    
    instance_status = fields.Selection([
        ('ok', 'OK'),
        ('impaired', 'Impaired'),
        ('insufficient-data', 'Insufficient Data'),
        ('not-applicable', 'Not Applicable'),
        ('initializing', 'Initializing')
    ], string='Instance Status', readonly=True, default='not-applicable',
    help='Status of the instance itself.')
    
    # Timing and Lifecycle
    launch_time = fields.Datetime(string='Launch Time', readonly=True,
                                 help='When the instance was launched.')
    termination_protection = fields.Boolean(string='Termination Protection', default=False,
                                           help='Whether termination protection is enabled.')
    
    # Tags and Metadata
    tags = fields.Text(string='Tags', 
                      help='JSON representation of the instance tags.')
    metadata = fields.Text(string='Metadata', readonly=True,
                          help='Additional metadata from the instance.')
    
    # Sync Status
    active = fields.Boolean(default=True)
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
        Create a new EC2 instance both in Odoo and AWS.
        """
        instance = super(EC2Instance, self).create(vals)
        if not self.env.context.get('import_from_aws', False):
            try:
                instance._launch_instance_in_aws()
            except Exception as e:
                instance.write({
                    'sync_status': 'error',
                    'sync_message': str(e),
                })
                _logger.error(f"Failed to launch EC2 instance: {str(e)}")
                raise UserError(f"Failed to launch EC2 instance: {str(e)}")
        return instance

    def write(self, vals):
        """
        Update EC2 instance in both Odoo and AWS.
        """
        result = super(EC2Instance, self).write(vals)
        if not self.env.context.get('import_from_aws', False):
            for instance in self:
                try:
                    # Only update specific fields that are supported for modification
                    update_fields = set(vals.keys()) & {
                        'name', 'instance_type', 'monitoring_enabled', 'termination_protection', 'tags'
                    }
                    if update_fields:
                        instance._update_instance_in_aws(update_fields)
                except Exception as e:
                    instance.write({
                        'sync_status': 'error',
                        'sync_message': str(e),
                    })
                    _logger.error(f"Failed to update EC2 instance {instance.instance_id}: {str(e)}")
        return result

    def unlink(self):
        """
        Terminate and delete the EC2 instance from AWS before removing from Odoo.
        """
        for instance in self:
            try:
                if instance.instance_id:
                    instance._terminate_instance_in_aws()
            except Exception as e:
                _logger.error(f"Failed to terminate EC2 instance {instance.instance_id}: {str(e)}")
                raise UserError(f"Failed to terminate EC2 instance: {str(e)}")
        return super(EC2Instance, self).unlink()

    def _launch_instance_in_aws(self):
        """
        Launch a new EC2 instance in AWS.
        """
        self.ensure_one()
        self.write({'sync_status': 'syncing'})
        
        # Initialize boto3 client
        ec2_client = self._get_boto3_client('ec2')
        
        # Prepare launch parameters
        params = {
            'ImageId': self.image_id,
            'InstanceType': self.instance_type,
            'MaxCount': 1,
            'MinCount': 1,
            'Monitoring': {'Enabled': self.monitoring_enabled},
        }
        
        # Add optional parameters if provided
        if self.key_pair_id and self.key_pair_id.key_name:
            params['KeyName'] = self.key_pair_id.key_name
        
        if self.subnet_id:
            params['SubnetId'] = self.subnet_id
        
        # Add security groups
        if self.security_group_ids:
            params['SecurityGroupIds'] = self.security_group_ids.mapped('group_id')
        
        # Add tags
        tags = [{'Key': 'Name', 'Value': self.name}]
        if self.tags:
            try:
                user_tags = json.loads(self.tags)
                for key, value in user_tags.items():
                    tags.append({'Key': key, 'Value': value})
            except Exception as e:
                _logger.warning(f"Could not parse tags JSON: {str(e)}")
        
        params['TagSpecifications'] = [
            {
                'ResourceType': 'instance',
                'Tags': tags
            }
        ]
        
        # Launch the instance
        response = ec2_client.run_instances(**params)
        
        # Update instance with AWS response data
        if response and 'Instances' in response and response['Instances']:
            instance_data = response['Instances'][0]
            instance_id = instance_data.get('InstanceId')
            
            # Wait for instance to initialize
            self._wait_for_instance_running(ec2_client, instance_id)
            
            # Get full instance details
            instance_info = self._get_instance_details(ec2_client, instance_id)
            
            # Update the record with AWS data
            self._update_from_aws_data(instance_info)
            
            # Enable termination protection if specified
            if self.termination_protection:
                ec2_client.modify_instance_attribute(
                    InstanceId=instance_id,
                    DisableApiTermination={'Value': True}
                )
            
            self.write({
                'sync_status': 'synced',
                'last_sync': fields.Datetime.now(),
                'sync_message': f'Successfully launched instance {instance_id}'
            })
            
            # Log the success
            self._log_aws_operation('launch_instance', 'success', 
                                   f"Successfully launched EC2 instance {instance_id}")
        else:
            raise UserError("Failed to launch EC2 instance: No instance data in response")

    def _wait_for_instance_running(self, ec2_client, instance_id, timeout=300, interval=10):
        """
        Wait for an instance to reach running state.
        
        Args:
            ec2_client: The boto3 EC2 client
            instance_id: The instance ID to wait for
            timeout: Maximum time to wait in seconds
            interval: Check interval in seconds
        
        Returns:
            True if instance is running, False if timed out
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            response = ec2_client.describe_instances(InstanceIds=[instance_id])
            if response and 'Reservations' in response and response['Reservations']:
                for reservation in response['Reservations']:
                    for instance in reservation['Instances']:
                        state = instance.get('State', {}).get('Name')
                        if state == 'running':
                            return True
                        elif state in ['terminated', 'shutting-down']:
                            raise UserError(f"Instance {instance_id} terminated unexpectedly")
            
            time.sleep(interval)
        
        return False

    def _get_instance_details(self, ec2_client, instance_id):
        """
        Get detailed information about an EC2 instance.
        
        Args:
            ec2_client: The boto3 EC2 client
            instance_id: The instance ID to query
        
        Returns:
            Dictionary with instance details
        """
        response = ec2_client.describe_instances(InstanceIds=[instance_id])
        if response and 'Reservations' in response and response['Reservations']:
            for reservation in response['Reservations']:
                for instance in reservation['Instances']:
                    if instance.get('InstanceId') == instance_id:
                        return instance
        
        raise UserError(f"Could not get details for instance {instance_id}")

    def _update_from_aws_data(self, instance_data):
        """
        Update the Odoo record with data from AWS response.
        
        Args:
            instance_data: Dictionary with instance data from AWS
        """
        # Extract basic instance data
        instance_id = instance_data.get('InstanceId')
        state = instance_data.get('State', {}).get('Name', 'pending')
        launch_time = instance_data.get('LaunchTime')
        
        # Network information
        public_ip = instance_data.get('PublicIpAddress', '')
        private_ip = instance_data.get('PrivateIpAddress', '')
        public_dns = instance_data.get('PublicDnsName', '')
        private_dns = instance_data.get('PrivateDnsName', '')
        vpc_id = instance_data.get('VpcId', '')
        subnet_id = instance_data.get('SubnetId', '')
        
        # Process tags
        name = self.name  # Default to current name
        tags_dict = {}
        
        if 'Tags' in instance_data:
            for tag in instance_data['Tags']:
                key = tag.get('Key', '')
                value = tag.get('Value', '')
                
                if key == 'Name':
                    name = value
                else:
                    tags_dict[key] = value
        
        # Update the record
        update_vals = {
            'instance_id': instance_id,
            'state': state,
            'launch_time': launch_time,
            'public_ip': public_ip,
            'private_ip': private_ip,
            'public_dns': public_dns,
            'private_dns': private_dns,
            'vpc_id': vpc_id,
            'subnet_id': subnet_id,
            'name': name,
        }
        
        # Only update tags if they changed
        if tags_dict:
            update_vals['tags'] = json.dumps(tags_dict)
        
        # Update with instance data using context to prevent recursion
        self.with_context(import_from_aws=True).write(update_vals)

    def _update_instance_in_aws(self, fields):
        """
        Update instance attributes in AWS based on changed fields.
        
        Args:
            fields: Set of field names that were changed
        """
        self.ensure_one()
        
        if not self.instance_id:
            raise UserError("Cannot update instance: No instance ID available")
        
        self.write({'sync_status': 'syncing'})
        ec2_client = self._get_boto3_client('ec2')
        
        try:
            # Update Name tag if name changed
            if 'name' in fields:
                response = ec2_client.create_tags(
                    Resources=[self.instance_id],
                    Tags=[{'Key': 'Name', 'Value': self.name}]
                )
            
            # Update custom tags
            if 'tags' in fields and self.tags:
                try:
                    tags_list = []
                    tags_dict = json.loads(self.tags)
                    for key, value in tags_dict.items():
                        tags_list.append({'Key': key, 'Value': value})
                    
                    if tags_list:
                        response = ec2_client.create_tags(
                            Resources=[self.instance_id],
                            Tags=tags_list
                        )
                except Exception as e:
                    _logger.warning(f"Could not update tags: {str(e)}")
            
            # Update instance type if changed and instance is stopped
            if 'instance_type' in fields:
                instance_state = self._get_instance_details(ec2_client, self.instance_id).get('State', {}).get('Name')
                if instance_state != 'stopped':
                    raise UserError("Cannot change instance type while instance is running. Please stop the instance first.")
                
                response = ec2_client.modify_instance_attribute(
                    InstanceId=self.instance_id,
                    InstanceType={'Value': self.instance_type}
                )
            
            # Update termination protection
            if 'termination_protection' in fields:
                response = ec2_client.modify_instance_attribute(
                    InstanceId=self.instance_id,
                    DisableApiTermination={'Value': self.termination_protection}
                )
            
            # Update monitoring
            if 'monitoring_enabled' in fields:
                if self.monitoring_enabled:
                    ec2_client.monitor_instances(InstanceIds=[self.instance_id])
                else:
                    ec2_client.unmonitor_instances(InstanceIds=[self.instance_id])
            
            self.write({
                'sync_status': 'synced',
                'last_sync': fields.Datetime.now(),
                'sync_message': f'Successfully updated instance {self.instance_id}'
            })
            
            # Log the success
            self._log_aws_operation('update_instance', 'success', 
                                   f"Successfully updated EC2 instance {self.instance_id}")
            
        except Exception as e:
            error_msg = f"Failed to update instance {self.instance_id}: {str(e)}"
            self.write({
                'sync_status': 'error',
                'sync_message': error_msg
            })
            self._log_aws_operation('update_instance', 'error', error_msg)
            raise UserError(error_msg)

    def _terminate_instance_in_aws(self):
        """
        Terminate an EC2 instance in AWS.
        """
        self.ensure_one()
        
        if not self.instance_id:
            return
        
        try:
            ec2_client = self._get_boto3_client('ec2')
            
            # Check termination protection
            if self.termination_protection:
                # Disable termination protection
                ec2_client.modify_instance_attribute(
                    InstanceId=self.instance_id,
                    DisableApiTermination={'Value': False}
                )
            
            # Terminate the instance
            response = ec2_client.terminate_instances(InstanceIds=[self.instance_id])
            
            # Log the success
            self._log_aws_operation('terminate_instance', 'success', 
                                   f"Successfully terminated EC2 instance {self.instance_id}")
            
        except Exception as e:
            error_msg = f"Failed to terminate instance {self.instance_id}: {str(e)}"
            self._log_aws_operation('terminate_instance', 'error', error_msg)
            raise UserError(error_msg)

    def action_start(self):
        """
        Start the EC2 instance.
        """
        for instance in self:
            if not instance.instance_id:
                continue
                
            try:
                ec2_client = instance._get_boto3_client('ec2')
                response = ec2_client.start_instances(InstanceIds=[instance.instance_id])
                
                instance.write({
                    'state': 'pending',
                    'sync_status': 'syncing',
                    'sync_message': f'Starting instance {instance.instance_id}'
                })
                
                # Log the action
                instance._log_aws_operation('start_instance', 'success', 
                                          f"Successfully started EC2 instance {instance.instance_id}")
                
                # Refresh instance data after a short delay
                self.env.cr.commit()  # Commit to ensure the state update is saved
                instance.refresh_instance_data()
                
            except Exception as e:
                error_msg = f"Failed to start instance {instance.instance_id}: {str(e)}"
                instance.write({
                    'sync_status': 'error',
                    'sync_message': error_msg
                })
                instance._log_aws_operation('start_instance', 'error', error_msg)
                raise UserError(error_msg)
        
        return True

    def action_stop(self):
        """
        Stop the EC2 instance.
        """
        for instance in self:
            if not instance.instance_id:
                continue
                
            try:
                ec2_client = instance._get_boto3_client('ec2')
                response = ec2_client.stop_instances(InstanceIds=[instance.instance_id])
                
                instance.write({
                    'state': 'stopping',
                    'sync_status': 'syncing',
                    'sync_message': f'Stopping instance {instance.instance_id}'
                })
                
                # Log the action
                instance._log_aws_operation('stop_instance', 'success', 
                                          f"Successfully stopping EC2 instance {instance.instance_id}")
                
                # Refresh instance data after a short delay
                self.env.cr.commit()  # Commit to ensure the state update is saved
                instance.refresh_instance_data()
                
            except Exception as e:
                error_msg = f"Failed to stop instance {instance.instance_id}: {str(e)}"
                instance.write({
                    'sync_status': 'error',
                    'sync_message': error_msg
                })
                instance._log_aws_operation('stop_instance', 'error', error_msg)
                raise UserError(error_msg)
        
        return True

    def action_reboot(self):
        """
        Reboot the EC2 instance.
        """
        for instance in self:
            if not instance.instance_id:
                continue
                
            try:
                ec2_client = instance._get_boto3_client('ec2')
                response = ec2_client.reboot_instances(InstanceIds=[instance.instance_id])
                
                instance.write({
                    'sync_status': 'syncing',
                    'sync_message': f'Rebooting instance {instance.instance_id}'
                })
                
                # Log the action
                instance._log_aws_operation('reboot_instance', 'success', 
                                          f"Successfully rebooted EC2 instance {instance.instance_id}")
                
                # Refresh instance data after a short delay
                self.env.cr.commit()  # Commit to ensure the state update is saved
                instance.refresh_instance_data()
                
            except Exception as e:
                error_msg = f"Failed to reboot instance {instance.instance_id}: {str(e)}"
                instance.write({
                    'sync_status': 'error',
                    'sync_message': error_msg
                })
                instance._log_aws_operation('reboot_instance', 'error', error_msg)
                raise UserError(error_msg)
        
        return True

    def refresh_instance_data(self):
        """
        Refresh instance data from AWS.
        """
        self.ensure_one()
        
        if not self.instance_id:
            return
        
        try:
            ec2_client = self._get_boto3_client('ec2')
            instance_data = self._get_instance_details(ec2_client, self.instance_id)
            self._update_from_aws_data(instance_data)
            
            # Update status
            try:
                status_response = ec2_client.describe_instance_status(InstanceIds=[self.instance_id])
                if status_response and 'InstanceStatuses' in status_response and status_response['InstanceStatuses']:
                    status = status_response['InstanceStatuses'][0]
                    self.with_context(import_from_aws=True).write({
                        'system_status': status.get('SystemStatus', {}).get('Status', 'insufficient-data'),
                        'instance_status': status.get('InstanceStatus', {}).get('Status', 'insufficient-data'),
                        'last_status_check': fields.Datetime.now()
                    })
            except Exception as e:
                _logger.warning(f"Could not get instance status: {str(e)}")
            
            self.write({
                'sync_status': 'synced',
                'last_sync': fields.Datetime.now(),
                'sync_message': f'Successfully refreshed instance data'
            })
            
        except Exception as e:
            error_msg = f"Failed to refresh instance data: {str(e)}"
            self.write({
                'sync_status': 'error',
                'sync_message': error_msg
            })
            _logger.error(error_msg)

    @api.model
    def import_instances_from_aws(self, aws_credentials_id=None, region_name=None):
        """
        Import EC2 instances from AWS.
        
        Args:
            aws_credentials_id: Optional AWS credentials ID
            region_name: Optional AWS region name
        
        Returns:
            Action to display imported instances
        """
        try:
            # Use provided credentials or default from context
            if not aws_credentials_id:
                aws_credentials_id = self.env.context.get('aws_credentials_id', False)
            
            if not region_name:
                region_name = self.env.context.get('aws_region', False)
            
            ec2_client = self._get_boto3_client('ec2', aws_credentials_id, region_name)
            
            # Get all instances
            response = ec2_client.describe_instances()
            
            imported_count = 0
            updated_count = 0
            
            if 'Reservations' in response:
                for reservation in response['Reservations']:
                    for instance_data in reservation.get('Instances', []):
                        instance_id = instance_data.get('InstanceId')
                        
                        # Skip if no instance ID
                        if not instance_id:
                            continue
                        
                        # Check if instance already exists
                        existing = self.search([('instance_id', '=', instance_id)], limit=1)
                        
                        # Extract name from tags
                        name = instance_id  # Default to instance ID
                        for tag in instance_data.get('Tags', []):
                            if tag.get('Key') == 'Name' and tag.get('Value'):
                                name = tag.get('Value')
                                break
                        
                        # Create or update the instance
                        if existing:
                            existing._update_from_aws_data(instance_data)
                            updated_count += 1
                        else:
                            # Create new instance record
                            vals = {
                                'name': name,
                                'instance_id': instance_id,
                                'instance_type': instance_data.get('InstanceType', ''),
                                'image_id': instance_data.get('ImageId', ''),
                                'vpc_id': instance_data.get('VpcId', ''),
                                'subnet_id': instance_data.get('SubnetId', ''),
                                'state': instance_data.get('State', {}).get('Name', 'pending'),
                                'aws_credentials_id': aws_credentials_id,
                                'aws_region': region_name or self._get_default_region(),
                            }
                            
                            # Create instance with context to prevent launching in AWS
                            new_instance = self.with_context(import_from_aws=True).create(vals)
                            
                            # Update with additional instance data
                            new_instance._update_from_aws_data(instance_data)
                            imported_count += 1
            
            # Show a success message
            message = f"Successfully imported {imported_count} new instances and updated {updated_count} existing instances."
            
            # Log the import operation
            self._log_aws_operation('import_instances', 'success', message)
            
            # Return action to display instances
            return {
                'name': _('Imported EC2 Instances'),
                'type': 'ir.actions.act_window',
                'res_model': 'aws.ec2.instance',
                'view_mode': 'tree,form',
                'target': 'current',
                'context': {
                    'default_aws_credentials_id': aws_credentials_id,
                    'default_aws_region': region_name or self._get_default_region(),
                },
                'help': message,
            }
            
        except Exception as e:
            error_msg = f"Failed to import EC2 instances: {str(e)}"
            self._log_aws_operation('import_instances', 'error', error_msg)
            raise UserError(error_msg)

    def refresh_all_instances(self):
        """
        Refresh all active instances.
        """
        instances = self.search([('active', '=', True)])
        for instance in instances:
            instance.refresh_instance_data()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Refresh Completed'),
                'message': _('%s instances have been refreshed from AWS EC2.') % len(instances),
                'sticky': False,
                'type': 'success',
            }
        }
    
    def sync_all_to_aws(self):
        """
        Sync all active instances to AWS EC2.
        Creates missing instances in AWS or updates existing ones.
        """
        instances = self.search([('active', '=', True)])
        success_count = 0
        error_messages = []
        
        for instance in instances:
            try:
                if not instance.instance_id:
                    # Launch in AWS if not already launched
                    instance._launch_instance_in_aws()
                    success_count += 1
                else:
                    # Update AWS instance with current Odoo data
                    instance._update_instance_in_aws(instance._fields.keys())
                    success_count += 1
            except Exception as e:
                error_message = f"Error syncing instance '{instance.name}': {str(e)}"
                _logger.error(error_message)
                error_messages.append(error_message)
                instance.write({
                    'sync_status': 'error',
                    'sync_message': error_message,
                })
        
        # Generate response message
        if error_messages:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sync Completed With Errors'),
                    'message': _(f"Successfully synced {success_count}/{len(instances)} instances to AWS EC2. Errors: {'; '.join(error_messages)}"),
                    'sticky': True,
                    'type': 'warning',
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sync Completed'),
                    'message': _(f"Successfully synced {success_count} instances to AWS EC2."),
                    'sticky': False,
                    'type': 'success',
                }
            }
            
    def action_launch_in_aws(self):
        """
        Launch this instance in AWS EC2.
        Public method that can be called from a button in a view.
        """
        self.ensure_one()
        
        try:
            if not self.instance_id:
                # Launch in AWS if not already launched
                self._launch_instance_in_aws()
                message = _("Instance '%s' has been created in AWS EC2.") % self.name
                
                self.write({
                    'sync_status': 'synced',
                    'last_sync': fields.Datetime.now(),
                    'sync_message': False,
                })
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Launch Successful'),
                        'message': message,
                        'sticky': False,
                        'type': 'success',
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Already Launched'),
                        'message': _("Instance '%s' is already launched in AWS EC2.") % self.name,
                        'sticky': False,
                        'type': 'warning',
                    }
                }
            
        except Exception as e:
            error_message = str(e)
            _logger.error("EC2 launch error for %s: %s", self.name, error_message)
            
            self.write({
                'sync_status': 'error',
                'sync_message': error_message,
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Launch Failed'),
                    'message': _(f"Failed to launch instance '{self.name}' in AWS EC2: {error_message}"),
                    'sticky': True,
                    'type': 'danger',
                }
            }
            
    def action_update_in_aws(self):
        """
        Update this instance in AWS EC2.
        Public method that can be called from a button in a view.
        """
        self.ensure_one()
        
        try:
            if self.instance_id:
                # Update AWS instance with current Odoo data
                self._update_instance_in_aws(self._fields.keys())
                message = _("Instance '%s' has been updated in AWS EC2.") % self.name
                
                self.write({
                    'sync_status': 'synced',
                    'last_sync': fields.Datetime.now(),
                    'sync_message': False,
                })
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Update Successful'),
                        'message': message,
                        'sticky': False,
                        'type': 'success',
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Not Launched'),
                        'message': _("Instance '%s' must be launched in AWS EC2 first.") % self.name,
                        'sticky': False,
                        'type': 'warning',
                    }
                }
                
        except Exception as e:
            error_message = str(e)
            _logger.error("EC2 update error for %s: %s", self.name, error_message)
            
            self.write({
                'sync_status': 'error',
                'sync_message': error_message,
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Update Failed'),
                    'message': _(f"Failed to update instance '{self.name}' in AWS EC2: {error_message}"),
                    'sticky': True,
                    'type': 'danger',
                }
            }