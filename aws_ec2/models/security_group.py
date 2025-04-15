# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
#
# Copyright (C) 2023 JAAH

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import json
import logging

_logger = logging.getLogger(__name__)

class EC2SecurityGroup(models.Model):
    """
    Represents an AWS EC2 security group.
    """
    _name = 'aws.ec2.security.group'
    _description = 'EC2 Security Group'
    _inherit = ['aws.service.implementation.mixin', 'aws.service.logger']
    _rec_name = 'name'
    _order = 'name'

    # Security Group Identifiers
    name = fields.Char(string='Name', required=True, index=True,
                      help='Name of the security group.')
    group_id = fields.Char(string='Security Group ID', readonly=True, index=True,
                          help='The unique ID of the security group (e.g. sg-0123456789abcdef0).')
    description = fields.Text(string='Description', 
                             help='Description of the security group.')
    
    # Network Settings
    vpc_id = fields.Char(string='VPC ID',
                        help='The VPC ID this security group belongs to.')
    
    # Rules
    inbound_rules = fields.Text(string='Inbound Rules', 
                               help='JSON representation of the inbound (ingress) rules.')
    outbound_rules = fields.Text(string='Outbound Rules', 
                                help='JSON representation of the outbound (egress) rules.')
    
    # Tags and Metadata
    tags = fields.Text(string='Tags', 
                      help='JSON representation of the security group tags.')
    
    # Usage Information
    instance_ids = fields.Many2many('aws.ec2.instance', string='Associated Instances', 
                                   compute='_compute_associated_instances',
                                   help='Instances using this security group.')
    instance_count = fields.Integer(string='Instance Count', compute='_compute_associated_instances',
                                   help='Number of instances using this security group.')
    
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

    def _compute_associated_instances(self):
        """
        Compute the instances associated with this security group.
        """
        for group in self:
            associated_instances = self.env['aws.ec2.instance'].search([
                ('security_group_ids', 'in', group.id)
            ])
            group.instance_ids = associated_instances
            group.instance_count = len(associated_instances)

    @api.model
    def create(self, vals):
        """
        Create a new security group both in Odoo and AWS.
        """
        group = super(EC2SecurityGroup, self).create(vals)
        if not self.env.context.get('import_from_aws', False):
            try:
                group._create_security_group_in_aws()
            except Exception as e:
                group.write({
                    'sync_status': 'error',
                    'sync_message': str(e),
                })
                _logger.error(f"Failed to create security group: {str(e)}")
                raise UserError(f"Failed to create security group: {str(e)}")
        return group

    def write(self, vals):
        """
        Update security group in both Odoo and AWS.
        """
        result = super(EC2SecurityGroup, self).write(vals)
        if not self.env.context.get('import_from_aws', False):
            for group in self:
                try:
                    # Only update specific fields that are supported for modification
                    update_fields = set(vals.keys()) & {
                        'description', 'inbound_rules', 'outbound_rules', 'tags'
                    }
                    if update_fields:
                        group._update_security_group_in_aws(update_fields)
                except Exception as e:
                    group.write({
                        'sync_status': 'error',
                        'sync_message': str(e),
                    })
                    _logger.error(f"Failed to update security group {group.group_id}: {str(e)}")
        return result

    def unlink(self):
        """
        Delete the security group from AWS before removing from Odoo.
        """
        for group in self:
            try:
                if group.group_id:
                    # Check if the security group is still in use
                    if group.instance_count > 0:
                        raise UserError(f"Cannot delete security group '{group.name}' as it is still being used by {group.instance_count} instances.")
                    
                    group._delete_security_group_from_aws()
            except Exception as e:
                _logger.error(f"Failed to delete security group {group.group_id}: {str(e)}")
                raise UserError(f"Failed to delete security group: {str(e)}")
        return super(EC2SecurityGroup, self).unlink()

    def _create_security_group_in_aws(self):
        """
        Create a new security group in AWS.
        """
        self.ensure_one()
        self.write({'sync_status': 'syncing'})
        
        # Initialize boto3 client
        ec2_client = self._get_boto3_client('ec2')
        
        # Prepare parameters
        params = {
            'Description': self.description or self.name,
            'GroupName': self.name,
        }
        
        # Add VPC ID if provided
        if self.vpc_id:
            params['VpcId'] = self.vpc_id
        
        # Create the security group
        response = ec2_client.create_security_group(**params)
        
        if 'GroupId' in response:
            group_id = response['GroupId']
            
            # Update the record with the new group ID
            self.write({
                'group_id': group_id,
            })
            
            # Add tags
            if self.tags:
                try:
                    tags_list = []
                    tags_dict = json.loads(self.tags)
                    for key, value in tags_dict.items():
                        tags_list.append({'Key': key, 'Value': str(value)})
                    
                    # Add name tag if not in custom tags
                    if not any(tag.get('Key') == 'Name' for tag in tags_list):
                        tags_list.append({'Key': 'Name', 'Value': self.name})
                    
                    if tags_list:
                        ec2_client.create_tags(
                            Resources=[group_id],
                            Tags=tags_list
                        )
                except Exception as e:
                    _logger.warning(f"Could not add tags to security group: {str(e)}")
            
            # Add ingress (inbound) rules
            if self.inbound_rules:
                try:
                    rules = json.loads(self.inbound_rules)
                    for rule in rules:
                        ingress_params = {
                            'GroupId': group_id,
                            'IpPermissions': [rule]
                        }
                        ec2_client.authorize_security_group_ingress(**ingress_params)
                except Exception as e:
                    _logger.warning(f"Could not add inbound rules to security group: {str(e)}")
            
            # Add egress (outbound) rules
            if self.outbound_rules:
                try:
                    # First revoke default outbound rule that allows all traffic
                    ec2_client.revoke_security_group_egress(
                        GroupId=group_id,
                        IpPermissions=[{
                            'IpProtocol': '-1',
                            'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                        }]
                    )
                    
                    # Then add custom rules
                    rules = json.loads(self.outbound_rules)
                    for rule in rules:
                        egress_params = {
                            'GroupId': group_id,
                            'IpPermissions': [rule]
                        }
                        ec2_client.authorize_security_group_egress(**egress_params)
                except Exception as e:
                    _logger.warning(f"Could not add outbound rules to security group: {str(e)}")
            
            self.write({
                'sync_status': 'synced',
                'last_sync': fields.Datetime.now(),
                'sync_message': f'Successfully created security group {group_id}'
            })
            
            # Log the success
            self._log_aws_operation('create_security_group', 'success', 
                                   f"Successfully created security group {group_id}")
        else:
            raise UserError("Failed to create security group: No group ID in response")

    def _update_security_group_in_aws(self, fields):
        """
        Update security group attributes in AWS based on changed fields.
        
        Args:
            fields: Set of field names that were changed
        """
        self.ensure_one()
        
        if not self.group_id:
            raise UserError("Cannot update security group: No group ID available")
        
        self.write({'sync_status': 'syncing'})
        ec2_client = self._get_boto3_client('ec2')
        
        try:
            # Update description (not directly supported in AWS, but we keep it in sync in Odoo)
            
            # Update tags
            if 'tags' in fields and self.tags:
                try:
                    # First remove existing tags
                    existing_tags_response = ec2_client.describe_tags(
                        Filters=[
                            {
                                'Name': 'resource-id',
                                'Values': [self.group_id]
                            }
                        ]
                    )
                    
                    existing_tags = []
                    for tag in existing_tags_response.get('Tags', []):
                        existing_tags.append({'Key': tag['Key']})
                    
                    if existing_tags:
                        ec2_client.delete_tags(
                            Resources=[self.group_id],
                            Tags=existing_tags
                        )
                    
                    # Then add new tags
                    tags_list = []
                    tags_dict = json.loads(self.tags)
                    for key, value in tags_dict.items():
                        tags_list.append({'Key': key, 'Value': str(value)})
                    
                    # Add name tag if not in custom tags
                    if not any(tag.get('Key') == 'Name' for tag in tags_list):
                        tags_list.append({'Key': 'Name', 'Value': self.name})
                    
                    if tags_list:
                        ec2_client.create_tags(
                            Resources=[self.group_id],
                            Tags=tags_list
                        )
                except Exception as e:
                    _logger.warning(f"Could not update tags: {str(e)}")
            
            # Update inbound (ingress) rules
            if 'inbound_rules' in fields:
                try:
                    # Get existing rules
                    sg_info = ec2_client.describe_security_groups(GroupIds=[self.group_id])
                    existing_rules = sg_info['SecurityGroups'][0]['IpPermissions']
                    
                    # Revoke all existing rules
                    if existing_rules:
                        ec2_client.revoke_security_group_ingress(
                            GroupId=self.group_id,
                            IpPermissions=existing_rules
                        )
                    
                    # Add new rules
                    if self.inbound_rules:
                        rules = json.loads(self.inbound_rules)
                        for rule in rules:
                            ingress_params = {
                                'GroupId': self.group_id,
                                'IpPermissions': [rule]
                            }
                            ec2_client.authorize_security_group_ingress(**ingress_params)
                except Exception as e:
                    _logger.warning(f"Could not update inbound rules: {str(e)}")
            
            # Update outbound (egress) rules
            if 'outbound_rules' in fields:
                try:
                    # Get existing rules
                    sg_info = ec2_client.describe_security_groups(GroupIds=[self.group_id])
                    existing_rules = sg_info['SecurityGroups'][0]['IpPermissionsEgress']
                    
                    # Revoke all existing rules
                    if existing_rules:
                        ec2_client.revoke_security_group_egress(
                            GroupId=self.group_id,
                            IpPermissions=existing_rules
                        )
                    
                    # Add new rules
                    if self.outbound_rules:
                        rules = json.loads(self.outbound_rules)
                        for rule in rules:
                            egress_params = {
                                'GroupId': self.group_id,
                                'IpPermissions': [rule]
                            }
                            ec2_client.authorize_security_group_egress(**egress_params)
                except Exception as e:
                    _logger.warning(f"Could not update outbound rules: {str(e)}")
            
            self.write({
                'sync_status': 'synced',
                'last_sync': fields.Datetime.now(),
                'sync_message': f'Successfully updated security group {self.group_id}'
            })
            
            # Log the success
            self._log_aws_operation('update_security_group', 'success', 
                                   f"Successfully updated security group {self.group_id}")
            
        except Exception as e:
            error_msg = f"Failed to update security group {self.group_id}: {str(e)}"
            self.write({
                'sync_status': 'error',
                'sync_message': error_msg
            })
            self._log_aws_operation('update_security_group', 'error', error_msg)
            raise UserError(error_msg)

    def _delete_security_group_from_aws(self):
        """
        Delete a security group from AWS.
        """
        self.ensure_one()
        
        if not self.group_id:
            return
        
        try:
            ec2_client = self._get_boto3_client('ec2')
            
            # Delete the security group
            ec2_client.delete_security_group(GroupId=self.group_id)
            
            # Log the success
            self._log_aws_operation('delete_security_group', 'success', 
                                   f"Successfully deleted security group {self.group_id}")
            
        except Exception as e:
            error_msg = f"Failed to delete security group {self.group_id}: {str(e)}"
            self._log_aws_operation('delete_security_group', 'error', error_msg)
            raise UserError(error_msg)

    def _refresh_security_group_data(self):
        """
        Refresh security group data from AWS.
        """
        self.ensure_one()
        
        if not self.group_id:
            return
        
        try:
            ec2_client = self._get_boto3_client('ec2')
            
            # Get security group details
            response = ec2_client.describe_security_groups(GroupIds=[self.group_id])
            
            if 'SecurityGroups' in response and response['SecurityGroups']:
                sg_data = response['SecurityGroups'][0]
                
                # Extract rules
                inbound_rules = sg_data.get('IpPermissions', [])
                outbound_rules = sg_data.get('IpPermissionsEgress', [])
                
                # Extract tags
                tags_dict = {}
                for tag in ec2_client.describe_tags(Filters=[{'Name': 'resource-id', 'Values': [self.group_id]}]).get('Tags', []):
                    if tag['Key'] != 'Name':  # Skip name tag as we store it separately
                        tags_dict[tag['Key']] = tag['Value']
                
                # Update the record
                self.with_context(import_from_aws=True).write({
                    'name': sg_data.get('GroupName', self.name),
                    'description': sg_data.get('Description', ''),
                    'vpc_id': sg_data.get('VpcId', ''),
                    'inbound_rules': json.dumps(inbound_rules) if inbound_rules else '',
                    'outbound_rules': json.dumps(outbound_rules) if outbound_rules else '',
                    'tags': json.dumps(tags_dict) if tags_dict else '',
                    'sync_status': 'synced',
                    'last_sync': fields.Datetime.now(),
                    'sync_message': f'Successfully refreshed security group data'
                })
                
            else:
                raise UserError(f"Security group {self.group_id} not found in AWS")
            
        except Exception as e:
            error_msg = f"Failed to refresh security group data: {str(e)}"
            self.write({
                'sync_status': 'error',
                'sync_message': error_msg
            })
            _logger.error(error_msg)

    @api.model
    def import_security_groups_from_aws(self, aws_credentials_id=None, region_name=None, vpc_id=None):
        """
        Import security groups from AWS.
        
        Args:
            aws_credentials_id: Optional AWS credentials ID
            region_name: Optional AWS region name
            vpc_id: Optional VPC ID to filter security groups
        
        Returns:
            Action to display imported security groups
        """
        try:
            # Use provided credentials or default from context
            if not aws_credentials_id:
                aws_credentials_id = self.env.context.get('aws_credentials_id', False)
            
            if not region_name:
                region_name = self.env.context.get('aws_region', False)
            
            ec2_client = self._get_boto3_client('ec2', aws_credentials_id, region_name)
            
            # Prepare filters
            filters = []
            if vpc_id:
                filters.append({
                    'Name': 'vpc-id',
                    'Values': [vpc_id]
                })
            
            # Get security groups
            if filters:
                response = ec2_client.describe_security_groups(Filters=filters)
            else:
                response = ec2_client.describe_security_groups()
            
            imported_count = 0
            updated_count = 0
            
            for sg_data in response.get('SecurityGroups', []):
                group_id = sg_data.get('GroupId')
                
                # Skip if no group ID
                if not group_id:
                    continue
                
                # Check if security group already exists
                existing = self.search([('group_id', '=', group_id)], limit=1)
                
                # Extract name and description
                name = sg_data.get('GroupName', '')
                description = sg_data.get('Description', '')
                vpc_id = sg_data.get('VpcId', '')
                
                # Extract rules
                inbound_rules = sg_data.get('IpPermissions', [])
                outbound_rules = sg_data.get('IpPermissionsEgress', [])
                
                # Extract tags
                tags_dict = {}
                for tag in ec2_client.describe_tags(Filters=[{'Name': 'resource-id', 'Values': [group_id]}]).get('Tags', []):
                    if tag['Key'] != 'Name':  # Skip name tag as we store it separately
                        tags_dict[tag['Key']] = tag['Value']
                
                # Create or update the security group
                if existing:
                    existing.with_context(import_from_aws=True).write({
                        'name': name,
                        'description': description,
                        'vpc_id': vpc_id,
                        'inbound_rules': json.dumps(inbound_rules) if inbound_rules else '',
                        'outbound_rules': json.dumps(outbound_rules) if outbound_rules else '',
                        'tags': json.dumps(tags_dict) if tags_dict else '',
                        'sync_status': 'synced',
                        'last_sync': fields.Datetime.now(),
                        'sync_message': f'Successfully imported from AWS'
                    })
                    updated_count += 1
                else:
                    # Create new security group record
                    self.with_context(import_from_aws=True).create({
                        'name': name,
                        'description': description,
                        'group_id': group_id,
                        'vpc_id': vpc_id,
                        'inbound_rules': json.dumps(inbound_rules) if inbound_rules else '',
                        'outbound_rules': json.dumps(outbound_rules) if outbound_rules else '',
                        'tags': json.dumps(tags_dict) if tags_dict else '',
                        'aws_credentials_id': aws_credentials_id,
                        'aws_region': region_name or self._get_default_region(),
                        'sync_status': 'synced',
                        'last_sync': fields.Datetime.now(),
                        'sync_message': f'Successfully imported from AWS'
                    })
                    imported_count += 1
            
            # Show a success message
            message = f"Successfully imported {imported_count} new security groups and updated {updated_count} existing security groups."
            
            # Log the import operation
            self._log_aws_operation('import_security_groups', 'success', message)
            
            # Return action to display security groups
            return {
                'name': _('Imported Security Groups'),
                'type': 'ir.actions.act_window',
                'res_model': 'aws.ec2.security.group',
                'view_mode': 'tree,form',
                'target': 'current',
                'context': {
                    'default_aws_credentials_id': aws_credentials_id,
                    'default_aws_region': region_name or self._get_default_region(),
                },
                'help': message,
            }
            
        except Exception as e:
            error_msg = f"Failed to import security groups: {str(e)}"
            self._log_aws_operation('import_security_groups', 'error', error_msg)
            raise UserError(error_msg)

    def refresh_all_security_groups(self):
        """
        Refresh all active security groups.
        """
        groups = self.search([('active', '=', True), ('group_id', '!=', False)])
        for group in groups:
            try:
                group._refresh_security_group_data()
            except Exception as e:
                _logger.error(f"Failed to refresh security group {group.group_id}: {str(e)}")
        
        # Return a notification message
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Security Group Refresh'),
                'message': _('Refreshed %s security groups.') % len(groups),
                'sticky': False,
                'type': 'success',
            }
        }