# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
#
# Copyright (C) 2023 JAAH

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import json
import logging

_logger = logging.getLogger(__name__)

class EC2VPC(models.Model):
    """
    Represents an AWS EC2 VPC (Virtual Private Cloud).
    """
    _name = 'aws.ec2.vpc'
    _description = 'EC2 VPC'
    _inherit = ['aws.service.implementation.mixin', 'aws.service.logger']
    _rec_name = 'name'
    _order = 'name'

    # VPC Identifiers
    name = fields.Char(string='Name', index=True,
                      help='Name of the VPC (tag:Name).')
    vpc_id = fields.Char(string='VPC ID', required=True, index=True,
                        help='The unique ID of the VPC (e.g. vpc-0123456789abcdef0).')
    
    # VPC Details
    cidr_block = fields.Char(string='CIDR Block', 
                            help='IP address range for the VPC in CIDR notation.')
    state = fields.Selection([
        ('pending', 'Pending'),
        ('available', 'Available')
    ], string='State', readonly=True, default='pending',
    help='Current state of the VPC.')
    
    is_default = fields.Boolean(string='Default VPC', readonly=True, default=False,
                               help='Whether this is the default VPC in the region.')
    
    # DNS Settings
    dns_support = fields.Boolean(string='DNS Support', default=True,
                                help='Whether DNS resolution is enabled for the VPC.')
    dns_hostnames = fields.Boolean(string='DNS Hostnames', default=True,
                                  help='Whether instances in the VPC get public DNS hostnames.')
    
    # Network Components
    subnet_ids = fields.One2many('aws.ec2.subnet', 'vpc_id', string='Subnets')
    subnet_count = fields.Integer(string='Subnet Count', compute='_compute_counts', store=True,
                                 help='Number of subnets in this VPC.')
    
    security_group_ids = fields.One2many('aws.ec2.security.group', 'vpc_id', string='Security Groups',
                                        compute='_compute_counts', store=True)
    security_group_count = fields.Integer(string='Security Group Count', compute='_compute_counts', store=True,
                                         help='Number of security groups in this VPC.')
    
    route_table_count = fields.Integer(string='Route Table Count', compute='_compute_counts', store=True,
                                      help='Number of route tables in this VPC.')
    
    network_acl_count = fields.Integer(string='Network ACL Count', compute='_compute_counts', store=True,
                                      help='Number of network ACLs in this VPC.')
    
    # Instance Information
    instance_ids = fields.One2many('aws.ec2.instance', 'vpc_id', string='Instances',
                                  compute='_compute_counts', store=True)
    instance_count = fields.Integer(string='Instance Count', compute='_compute_counts', store=True,
                                   help='Number of instances in this VPC.')
    
    # Tags and Metadata
    tags = fields.Text(string='Tags', 
                      help='JSON representation of the VPC tags.')
    
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

    @api.depends('vpc_id', 'subnet_ids')
    def _compute_counts(self):
        """
        Compute the counts of related resources.
        """
        for vpc in self:
            # Count subnets - use subnet_ids One2many field for counting
            vpc.subnet_count = len(vpc.subnet_ids)
            
            # Count instances
            instances = self.env['aws.ec2.instance'].search([
                ('vpc_id', '=', vpc.vpc_id)
            ])
            vpc.instance_ids = instances
            vpc.instance_count = len(instances)
            
            # Count security groups
            security_groups = self.env['aws.ec2.security.group'].search([
                ('vpc_id', '=', vpc.vpc_id)
            ])
            vpc.security_group_ids = security_groups
            vpc.security_group_count = len(security_groups)
            
            # Initialize other counts (to be implemented with those models)
            vpc.route_table_count = 0
            vpc.network_acl_count = 0

    @api.model
    def create(self, vals):
        """
        Create a new VPC both in Odoo and AWS.
        """
        vpc = super(EC2VPC, self).create(vals)
        if not self.env.context.get('import_from_aws', False):
            try:
                vpc._create_vpc_in_aws()
            except Exception as e:
                vpc.write({
                    'sync_status': 'error',
                    'sync_message': str(e),
                })
                _logger.error(f"Failed to create VPC: {str(e)}")
                raise UserError(f"Failed to create VPC: {str(e)}")
        return vpc

    def write(self, vals):
        """
        Update VPC in both Odoo and AWS.
        """
        result = super(EC2VPC, self).write(vals)
        if not self.env.context.get('import_from_aws', False):
            for vpc in self:
                try:
                    # Only update specific fields that are supported for modification
                    update_fields = set(vals.keys()) & {
                        'name', 'dns_support', 'dns_hostnames', 'tags'
                    }
                    if update_fields:
                        vpc._update_vpc_in_aws(update_fields)
                except Exception as e:
                    vpc.write({
                        'sync_status': 'error',
                        'sync_message': str(e),
                    })
                    _logger.error(f"Failed to update VPC {vpc.vpc_id}: {str(e)}")
        return result

    def unlink(self):
        """
        Delete the VPC from AWS before removing from Odoo.
        """
        for vpc in self:
            try:
                if vpc.vpc_id and not vpc.is_default:  # Prevent deletion of default VPC
                    # Check if the VPC has dependent resources
                    if vpc.subnet_count > 0:
                        raise UserError(f"Cannot delete VPC '{vpc.name}' as it contains {vpc.subnet_count} subnets. Delete the subnets first.")
                    
                    if vpc.instance_count > 0:
                        raise UserError(f"Cannot delete VPC '{vpc.name}' as it contains {vpc.instance_count} instances. Terminate the instances first.")
                    
                    if vpc.security_group_count > 0:
                        raise UserError(f"Cannot delete VPC '{vpc.name}' as it contains {vpc.security_group_count} security groups. Delete the security groups first.")
                    
                    vpc._delete_vpc_from_aws()
            except Exception as e:
                _logger.error(f"Failed to delete VPC {vpc.vpc_id}: {str(e)}")
                raise UserError(f"Failed to delete VPC: {str(e)}")
        return super(EC2VPC, self).unlink()

    def _create_vpc_in_aws(self):
        """
        Create a new VPC in AWS.
        """
        self.ensure_one()
        self.write({'sync_status': 'syncing'})
        
        # Initialize boto3 client
        ec2_client = self._get_boto3_client('ec2')
        
        try:
            # Create the VPC
            response = ec2_client.create_vpc(
                CidrBlock=self.cidr_block,
                AmazonProvidedIpv6CidrBlock=False,
                InstanceTenancy='default'
            )
            
            if 'Vpc' in response:
                vpc_id = response['Vpc']['VpcId']
                
                # Update the record with the VPC ID
                self.write({
                    'vpc_id': vpc_id,
                    'state': response['Vpc'].get('State', 'pending')
                })
                
                # Wait for the VPC to be available
                ec2_client.get_waiter('vpc_available').wait(VpcIds=[vpc_id])
                
                # Add name tag
                ec2_client.create_tags(
                    Resources=[vpc_id],
                    Tags=[{'Key': 'Name', 'Value': self.name}]
                )
                
                # Add custom tags if provided
                if self.tags:
                    try:
                        tags_list = []
                        tags_dict = json.loads(self.tags)
                        for key, value in tags_dict.items():
                            if key != 'Name':  # Skip name tag as we added it above
                                tags_list.append({'Key': key, 'Value': str(value)})
                        
                        if tags_list:
                            ec2_client.create_tags(
                                Resources=[vpc_id],
                                Tags=tags_list
                            )
                    except Exception as e:
                        _logger.warning(f"Could not add tags to VPC: {str(e)}")
                
                # Configure DNS settings
                ec2_client.modify_vpc_attribute(
                    VpcId=vpc_id,
                    EnableDnsSupport={'Value': self.dns_support}
                )
                
                ec2_client.modify_vpc_attribute(
                    VpcId=vpc_id,
                    EnableDnsHostnames={'Value': self.dns_hostnames}
                )
                
                # Update sync status
                self.write({
                    'sync_status': 'synced',
                    'last_sync': fields.Datetime.now(),
                    'sync_message': f'Successfully created VPC {vpc_id}'
                })
                
                # Log the success
                self._log_aws_operation('create_vpc', 'success', 
                                       f"Successfully created VPC {vpc_id}")
                
            else:
                raise UserError("Failed to create VPC: No VPC data in response")
                
        except Exception as e:
            error_msg = f"Failed to create VPC: {str(e)}"
            self.write({
                'sync_status': 'error',
                'sync_message': error_msg
            })
            self._log_aws_operation('create_vpc', 'error', error_msg)
            raise UserError(error_msg)

    def _update_vpc_in_aws(self, fields):
        """
        Update VPC attributes in AWS based on changed fields.
        
        Args:
            fields: Set of field names that were changed
        """
        self.ensure_one()
        
        if not self.vpc_id:
            raise UserError("Cannot update VPC: No VPC ID available")
        
        self.write({'sync_status': 'syncing'})
        ec2_client = self._get_boto3_client('ec2')
        
        try:
            # Update name tag if name changed
            if 'name' in fields:
                ec2_client.create_tags(
                    Resources=[self.vpc_id],
                    Tags=[{'Key': 'Name', 'Value': self.name}]
                )
            
            # Update DNS support setting
            if 'dns_support' in fields:
                ec2_client.modify_vpc_attribute(
                    VpcId=self.vpc_id,
                    EnableDnsSupport={'Value': self.dns_support}
                )
            
            # Update DNS hostnames setting
            if 'dns_hostnames' in fields:
                ec2_client.modify_vpc_attribute(
                    VpcId=self.vpc_id,
                    EnableDnsHostnames={'Value': self.dns_hostnames}
                )
            
            # Update custom tags
            if 'tags' in fields and self.tags:
                try:
                    # First get existing tags
                    response = ec2_client.describe_tags(
                        Filters=[
                            {'Name': 'resource-id', 'Values': [self.vpc_id]}
                        ]
                    )
                    
                    # Delete all existing tags except the Name tag
                    existing_tags = []
                    for tag in response.get('Tags', []):
                        if tag['Key'] != 'Name':
                            existing_tags.append({'Key': tag['Key']})
                    
                    if existing_tags:
                        ec2_client.delete_tags(
                            Resources=[self.vpc_id],
                            Tags=existing_tags
                        )
                    
                    # Add new tags
                    tags_list = []
                    tags_dict = json.loads(self.tags)
                    for key, value in tags_dict.items():
                        if key != 'Name':  # Skip name tag as we handle it separately
                            tags_list.append({'Key': key, 'Value': str(value)})
                    
                    if tags_list:
                        ec2_client.create_tags(
                            Resources=[self.vpc_id],
                            Tags=tags_list
                        )
                except Exception as e:
                    _logger.warning(f"Could not update tags: {str(e)}")
            
            # Update sync status
            self.write({
                'sync_status': 'synced',
                'last_sync': fields.Datetime.now(),
                'sync_message': f'Successfully updated VPC {self.vpc_id}'
            })
            
            # Log the success
            self._log_aws_operation('update_vpc', 'success', 
                                   f"Successfully updated VPC {self.vpc_id}")
            
        except Exception as e:
            error_msg = f"Failed to update VPC {self.vpc_id}: {str(e)}"
            self.write({
                'sync_status': 'error',
                'sync_message': error_msg
            })
            self._log_aws_operation('update_vpc', 'error', error_msg)
            raise UserError(error_msg)

    def _delete_vpc_from_aws(self):
        """
        Delete a VPC from AWS.
        """
        self.ensure_one()
        
        if not self.vpc_id:
            return
        
        if self.is_default:
            raise UserError("Cannot delete the default VPC.")
        
        try:
            ec2_client = self._get_boto3_client('ec2')
            
            # Delete the VPC
            ec2_client.delete_vpc(VpcId=self.vpc_id)
            
            # Log the success
            self._log_aws_operation('delete_vpc', 'success', 
                                   f"Successfully deleted VPC {self.vpc_id}")
            
        except Exception as e:
            error_msg = f"Failed to delete VPC {self.vpc_id}: {str(e)}"
            self._log_aws_operation('delete_vpc', 'error', error_msg)
            raise UserError(error_msg)

    def refresh_vpc_data(self):
        """
        Refresh VPC data from AWS.
        """
        self.ensure_one()
        
        if not self.vpc_id:
            return
        
        try:
            ec2_client = self._get_boto3_client('ec2')
            
            # Get VPC details
            response = ec2_client.describe_vpcs(VpcIds=[self.vpc_id])
            
            if 'Vpcs' in response and response['Vpcs']:
                vpc_data = response['Vpcs'][0]
                
                # Extract details
                state = vpc_data.get('State', 'pending')
                cidr_block = vpc_data.get('CidrBlock', '')
                is_default = vpc_data.get('IsDefault', False)
                
                # Extract tags
                name = self.vpc_id
                tags_dict = {}
                
                for tag in ec2_client.describe_tags(
                    Filters=[{'Name': 'resource-id', 'Values': [self.vpc_id]}]
                ).get('Tags', []):
                    if tag['Key'] == 'Name':
                        name = tag['Value']
                    else:
                        tags_dict[tag['Key']] = tag['Value']
                
                # Get DNS settings
                dns_support = True
                try:
                    dns_support_response = ec2_client.describe_vpc_attribute(
                        VpcId=self.vpc_id,
                        Attribute='enableDnsSupport'
                    )
                    dns_support = dns_support_response.get('EnableDnsSupport', {}).get('Value', True)
                except Exception as e:
                    _logger.warning(f"Could not get DNS support setting: {str(e)}")
                
                dns_hostnames = True
                try:
                    dns_hostnames_response = ec2_client.describe_vpc_attribute(
                        VpcId=self.vpc_id,
                        Attribute='enableDnsHostnames'
                    )
                    dns_hostnames = dns_hostnames_response.get('EnableDnsHostnames', {}).get('Value', True)
                except Exception as e:
                    _logger.warning(f"Could not get DNS hostnames setting: {str(e)}")
                
                # Update the record
                self.with_context(import_from_aws=True).write({
                    'name': name,
                    'cidr_block': cidr_block,
                    'state': state,
                    'is_default': is_default,
                    'dns_support': dns_support,
                    'dns_hostnames': dns_hostnames,
                    'tags': json.dumps(tags_dict) if tags_dict else '',
                    'sync_status': 'synced',
                    'last_sync': fields.Datetime.now(),
                    'sync_message': f'Successfully refreshed VPC data'
                })
                
            else:
                raise UserError(f"VPC {self.vpc_id} not found in AWS")
                
        except Exception as e:
            error_msg = f"Failed to refresh VPC data: {str(e)}"
            self.write({
                'sync_status': 'error',
                'sync_message': error_msg
            })
            _logger.error(error_msg)

    @api.model
    def import_vpcs_from_aws(self, aws_credentials_id=None, region_name=None):
        """
        Import VPCs from AWS.
        
        Args:
            aws_credentials_id: Optional AWS credentials ID
            region_name: Optional AWS region name
        
        Returns:
            Action to display imported VPCs
        """
        try:
            # Use provided credentials or default from context
            if not aws_credentials_id:
                aws_credentials_id = self.env.context.get('aws_credentials_id', False)
            
            if not region_name:
                region_name = self.env.context.get('aws_region', False)
            
            ec2_client = self._get_boto3_client('ec2', aws_credentials_id, region_name)
            
            # Get all VPCs
            response = ec2_client.describe_vpcs()
            
            imported_count = 0
            updated_count = 0
            
            for vpc_data in response.get('Vpcs', []):
                vpc_id = vpc_data.get('VpcId')
                
                # Skip if no VPC ID
                if not vpc_id:
                    continue
                
                # Check if VPC already exists
                existing = self.search([('vpc_id', '=', vpc_id)], limit=1)
                
                # Extract details
                state = vpc_data.get('State', 'pending')
                cidr_block = vpc_data.get('CidrBlock', '')
                is_default = vpc_data.get('IsDefault', False)
                
                # Extract tags
                name = vpc_id
                tags_dict = {}
                
                for tag in ec2_client.describe_tags(
                    Filters=[{'Name': 'resource-id', 'Values': [vpc_id]}]
                ).get('Tags', []):
                    if tag['Key'] == 'Name':
                        name = tag['Value']
                    else:
                        tags_dict[tag['Key']] = tag['Value']
                
                # Get DNS settings
                dns_support = True
                try:
                    dns_support_response = ec2_client.describe_vpc_attribute(
                        VpcId=vpc_id,
                        Attribute='enableDnsSupport'
                    )
                    dns_support = dns_support_response.get('EnableDnsSupport', {}).get('Value', True)
                except Exception as e:
                    _logger.warning(f"Could not get DNS support setting: {str(e)}")
                
                dns_hostnames = True
                try:
                    dns_hostnames_response = ec2_client.describe_vpc_attribute(
                        VpcId=vpc_id,
                        Attribute='enableDnsHostnames'
                    )
                    dns_hostnames = dns_hostnames_response.get('EnableDnsHostnames', {}).get('Value', True)
                except Exception as e:
                    _logger.warning(f"Could not get DNS hostnames setting: {str(e)}")
                
                # Create or update the VPC record
                if existing:
                    existing.with_context(import_from_aws=True).write({
                        'name': name,
                        'cidr_block': cidr_block,
                        'state': state,
                        'is_default': is_default,
                        'dns_support': dns_support,
                        'dns_hostnames': dns_hostnames,
                        'tags': json.dumps(tags_dict) if tags_dict else '',
                        'sync_status': 'synced',
                        'last_sync': fields.Datetime.now(),
                        'sync_message': f'Successfully imported from AWS'
                    })
                    updated_count += 1
                else:
                    # Create new VPC record
                    self.with_context(import_from_aws=True).create({
                        'name': name,
                        'vpc_id': vpc_id,
                        'cidr_block': cidr_block,
                        'state': state,
                        'is_default': is_default,
                        'dns_support': dns_support,
                        'dns_hostnames': dns_hostnames,
                        'tags': json.dumps(tags_dict) if tags_dict else '',
                        'aws_credentials_id': aws_credentials_id,
                        'aws_region': region_name or self._get_default_region(),
                        'sync_status': 'synced',
                        'last_sync': fields.Datetime.now(),
                        'sync_message': f'Successfully imported from AWS'
                    })
                    imported_count += 1
            
            # Show a success message
            message = f"Successfully imported {imported_count} new VPCs and updated {updated_count} existing VPCs."
            
            # Log the import operation
            self._log_aws_operation('import_vpcs', 'success', message)
            
            # Return action to display VPCs
            return {
                'name': _('Imported VPCs'),
                'type': 'ir.actions.act_window',
                'res_model': 'aws.ec2.vpc',
                'view_mode': 'tree,form',
                'target': 'current',
                'context': {
                    'default_aws_credentials_id': aws_credentials_id,
                    'default_aws_region': region_name or self._get_default_region(),
                },
                'help': message,
            }
            
        except Exception as e:
            error_msg = f"Failed to import VPCs: {str(e)}"
            self._log_aws_operation('import_vpcs', 'error', error_msg)
            raise UserError(error_msg)

    def refresh_all_vpcs(self):
        """
        Refresh all active VPCs.
        """
        vpcs = self.search([('active', '=', True), ('vpc_id', '!=', False)])
        for vpc in vpcs:
            try:
                vpc.refresh_vpc_data()
            except Exception as e:
                _logger.error(f"Failed to refresh VPC {vpc.vpc_id}: {str(e)}")
        
        # Return a notification message
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('VPC Refresh'),
                'message': _('Refreshed %s VPCs.') % len(vpcs),
                'sticky': False,
                'type': 'success',
            }
        }