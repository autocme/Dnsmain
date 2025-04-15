# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
#
# Copyright (C) 2023 JAAH

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import json
import logging

_logger = logging.getLogger(__name__)

class EC2Subnet(models.Model):
    """
    Represents an AWS EC2 Subnet within a VPC.
    """
    _name = 'aws.ec2.subnet'
    _description = 'EC2 Subnet'
    _inherit = ['aws.service.implementation.mixin', 'aws.service.logger']
    _rec_name = 'name'
    _order = 'name'

    # Subnet Identifiers
    name = fields.Char(string='Name', index=True,
                      help='Name of the subnet (tag:Name).')
    subnet_id = fields.Char(string='Subnet ID', required=True, index=True,
                           help='The unique ID of the subnet (e.g. subnet-0123456789abcdef0).')
    
    # Subnet Details
    vpc_id = fields.Many2one('aws.ec2.vpc', string='VPC', required=True, ondelete='cascade',
                            help='The VPC this subnet belongs to.')
    cidr_block = fields.Char(string='CIDR Block', required=True,
                            help='IP address range for the subnet in CIDR notation.')
    availability_zone = fields.Char(string='Availability Zone',
                                   help='The Availability Zone where the subnet is located.')
    state = fields.Selection([
        ('pending', 'Pending'),
        ('available', 'Available')
    ], string='State', readonly=True, default='pending',
    help='Current state of the subnet.')
    
    # Network Settings
    map_public_ip = fields.Boolean(string='Auto-assign Public IP', default=False,
                                  help='Whether instances launched in this subnet get a public IP by default.')
    default_for_az = fields.Boolean(string='Default for AZ', readonly=True, default=False,
                                   help='Whether this is the default subnet for the Availability Zone.')
    
    # Capacity
    available_ip_address_count = fields.Integer(string='Available IP Addresses', readonly=True,
                                              help='Number of available IP addresses in this subnet.')
    
    # Route Table
    route_table_id = fields.Char(string='Route Table ID',
                                help='The route table associated with this subnet.')
    
    # Instance Information
    instance_ids = fields.One2many('aws.ec2.instance', 'subnet_id', string='Instances',
                                  compute='_compute_instances')
    instance_count = fields.Integer(string='Instance Count', compute='_compute_instances', store=True,
                                   help='Number of instances in this subnet.')
    
    # Tags and Metadata
    tags = fields.Text(string='Tags', 
                      help='JSON representation of the subnet tags.')
    
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

    @api.depends('subnet_id')
    def _compute_instances(self):
        """
        Compute the instances in this subnet.
        """
        for subnet in self:
            instances = self.env['aws.ec2.instance'].search([
                ('subnet_id', '=', subnet.subnet_id)
            ])
            subnet.instance_ids = instances
            subnet.instance_count = len(instances)

    @api.model
    def create(self, vals):
        """
        Create a new subnet both in Odoo and AWS.
        """
        subnet = super(EC2Subnet, self).create(vals)
        if not self.env.context.get('import_from_aws', False):
            try:
                subnet._create_subnet_in_aws()
            except Exception as e:
                subnet.write({
                    'sync_status': 'error',
                    'sync_message': str(e),
                })
                _logger.error(f"Failed to create subnet: {str(e)}")
                raise UserError(f"Failed to create subnet: {str(e)}")
        return subnet

    def write(self, vals):
        """
        Update subnet in both Odoo and AWS.
        """
        result = super(EC2Subnet, self).write(vals)
        if not self.env.context.get('import_from_aws', False):
            for subnet in self:
                try:
                    # Only update specific fields that are supported for modification
                    update_fields = set(vals.keys()) & {
                        'name', 'map_public_ip', 'tags'
                    }
                    if update_fields:
                        subnet._update_subnet_in_aws(update_fields)
                except Exception as e:
                    subnet.write({
                        'sync_status': 'error',
                        'sync_message': str(e),
                    })
                    _logger.error(f"Failed to update subnet {subnet.subnet_id}: {str(e)}")
        return result

    def unlink(self):
        """
        Delete the subnet from AWS before removing from Odoo.
        """
        for subnet in self:
            try:
                if subnet.subnet_id:
                    # Check if the subnet has instances
                    if subnet.instance_count > 0:
                        raise UserError(f"Cannot delete subnet '{subnet.name}' as it contains {subnet.instance_count} instances. Terminate the instances first.")
                    
                    subnet._delete_subnet_from_aws()
            except Exception as e:
                _logger.error(f"Failed to delete subnet {subnet.subnet_id}: {str(e)}")
                raise UserError(f"Failed to delete subnet: {str(e)}")
        return super(EC2Subnet, self).unlink()

    def _create_subnet_in_aws(self):
        """
        Create a new subnet in AWS.
        """
        self.ensure_one()
        self.write({'sync_status': 'syncing'})
        
        # Initialize boto3 client
        ec2_client = self._get_boto3_client('ec2')
        
        # Get the VPC ID
        vpc = self.vpc_id
        if not vpc or not vpc.vpc_id:
            raise UserError("Invalid VPC selected")
        
        try:
            # Create the subnet
            params = {
                'VpcId': vpc.vpc_id,
                'CidrBlock': self.cidr_block,
            }
            
            if self.availability_zone:
                params['AvailabilityZone'] = self.availability_zone
            
            response = ec2_client.create_subnet(**params)
            
            if 'Subnet' in response:
                subnet_id = response['Subnet']['SubnetId']
                
                # Update the record with the subnet ID
                self.write({
                    'subnet_id': subnet_id,
                    'state': response['Subnet'].get('State', 'pending'),
                    'available_ip_address_count': response['Subnet'].get('AvailableIpAddressCount', 0),
                    'availability_zone': response['Subnet'].get('AvailabilityZone', '')
                })
                
                # Wait for the subnet to be available
                ec2_client.get_waiter('subnet_available').wait(SubnetIds=[subnet_id])
                
                # Add name tag
                ec2_client.create_tags(
                    Resources=[subnet_id],
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
                                Resources=[subnet_id],
                                Tags=tags_list
                            )
                    except Exception as e:
                        _logger.warning(f"Could not add tags to subnet: {str(e)}")
                
                # Configure map public IP setting
                ec2_client.modify_subnet_attribute(
                    SubnetId=subnet_id,
                    MapPublicIpOnLaunch={'Value': self.map_public_ip}
                )
                
                # Update sync status
                self.write({
                    'sync_status': 'synced',
                    'last_sync': fields.Datetime.now(),
                    'sync_message': f'Successfully created subnet {subnet_id}'
                })
                
                # Log the success
                self._log_aws_operation('create_subnet', 'success', 
                                       f"Successfully created subnet {subnet_id}")
                
            else:
                raise UserError("Failed to create subnet: No subnet data in response")
                
        except Exception as e:
            error_msg = f"Failed to create subnet: {str(e)}"
            self.write({
                'sync_status': 'error',
                'sync_message': error_msg
            })
            self._log_aws_operation('create_subnet', 'error', error_msg)
            raise UserError(error_msg)

    def _update_subnet_in_aws(self, fields):
        """
        Update subnet attributes in AWS based on changed fields.
        
        Args:
            fields: Set of field names that were changed
        """
        self.ensure_one()
        
        if not self.subnet_id:
            raise UserError("Cannot update subnet: No subnet ID available")
        
        self.write({'sync_status': 'syncing'})
        ec2_client = self._get_boto3_client('ec2')
        
        try:
            # Update name tag if name changed
            if 'name' in fields:
                ec2_client.create_tags(
                    Resources=[self.subnet_id],
                    Tags=[{'Key': 'Name', 'Value': self.name}]
                )
            
            # Update map public IP setting
            if 'map_public_ip' in fields:
                ec2_client.modify_subnet_attribute(
                    SubnetId=self.subnet_id,
                    MapPublicIpOnLaunch={'Value': self.map_public_ip}
                )
            
            # Update custom tags
            if 'tags' in fields and self.tags:
                try:
                    # First get existing tags
                    response = ec2_client.describe_tags(
                        Filters=[
                            {'Name': 'resource-id', 'Values': [self.subnet_id]}
                        ]
                    )
                    
                    # Delete all existing tags except the Name tag
                    existing_tags = []
                    for tag in response.get('Tags', []):
                        if tag['Key'] != 'Name':
                            existing_tags.append({'Key': tag['Key']})
                    
                    if existing_tags:
                        ec2_client.delete_tags(
                            Resources=[self.subnet_id],
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
                            Resources=[self.subnet_id],
                            Tags=tags_list
                        )
                except Exception as e:
                    _logger.warning(f"Could not update tags: {str(e)}")
            
            # Update sync status
            self.write({
                'sync_status': 'synced',
                'last_sync': fields.Datetime.now(),
                'sync_message': f'Successfully updated subnet {self.subnet_id}'
            })
            
            # Log the success
            self._log_aws_operation('update_subnet', 'success', 
                                   f"Successfully updated subnet {self.subnet_id}")
            
        except Exception as e:
            error_msg = f"Failed to update subnet {self.subnet_id}: {str(e)}"
            self.write({
                'sync_status': 'error',
                'sync_message': error_msg
            })
            self._log_aws_operation('update_subnet', 'error', error_msg)
            raise UserError(error_msg)

    def _delete_subnet_from_aws(self):
        """
        Delete a subnet from AWS.
        """
        self.ensure_one()
        
        if not self.subnet_id:
            return
        
        try:
            ec2_client = self._get_boto3_client('ec2')
            
            # Delete the subnet
            ec2_client.delete_subnet(SubnetId=self.subnet_id)
            
            # Log the success
            self._log_aws_operation('delete_subnet', 'success', 
                                   f"Successfully deleted subnet {self.subnet_id}")
            
        except Exception as e:
            error_msg = f"Failed to delete subnet {self.subnet_id}: {str(e)}"
            self._log_aws_operation('delete_subnet', 'error', error_msg)
            raise UserError(error_msg)

    def refresh_subnet_data(self):
        """
        Refresh subnet data from AWS.
        """
        self.ensure_one()
        
        if not self.subnet_id:
            return
        
        try:
            ec2_client = self._get_boto3_client('ec2')
            
            # Get subnet details
            response = ec2_client.describe_subnets(SubnetIds=[self.subnet_id])
            
            if 'Subnets' in response and response['Subnets']:
                subnet_data = response['Subnets'][0]
                
                # Extract details
                state = subnet_data.get('State', 'pending')
                cidr_block = subnet_data.get('CidrBlock', '')
                availability_zone = subnet_data.get('AvailabilityZone', '')
                available_ip_address_count = subnet_data.get('AvailableIpAddressCount', 0)
                default_for_az = subnet_data.get('DefaultForAz', False)
                vpc_id = subnet_data.get('VpcId', '')
                
                # Extract tags
                name = self.subnet_id
                tags_dict = {}
                
                for tag in ec2_client.describe_tags(
                    Filters=[{'Name': 'resource-id', 'Values': [self.subnet_id]}]
                ).get('Tags', []):
                    if tag['Key'] == 'Name':
                        name = tag['Value']
                    else:
                        tags_dict[tag['Key']] = tag['Value']
                
                # Get map public IP setting
                map_public_ip = False
                try:
                    map_public_ip_response = ec2_client.describe_subnet_attribute(
                        SubnetId=self.subnet_id,
                        Attribute='mapPublicIpOnLaunch'
                    )
                    map_public_ip = map_public_ip_response.get('MapPublicIpOnLaunch', {}).get('Value', False)
                except Exception as e:
                    _logger.warning(f"Could not get map public IP setting: {str(e)}")
                
                # Get route table association
                route_table_id = ''
                try:
                    route_tables_response = ec2_client.describe_route_tables(
                        Filters=[{'Name': 'association.subnet-id', 'Values': [self.subnet_id]}]
                    )
                    if route_tables_response.get('RouteTables'):
                        for route_table in route_tables_response['RouteTables']:
                            for association in route_table.get('Associations', []):
                                if association.get('SubnetId') == self.subnet_id:
                                    route_table_id = route_table.get('RouteTableId', '')
                                    break
                except Exception as e:
                    _logger.warning(f"Could not get route table association: {str(e)}")
                
                # Get VPC record
                vpc = self.env['aws.ec2.vpc'].search([('vpc_id', '=', vpc_id)], limit=1)
                
                # Update the record
                self.with_context(import_from_aws=True).write({
                    'name': name,
                    'cidr_block': cidr_block,
                    'state': state,
                    'availability_zone': availability_zone,
                    'available_ip_address_count': available_ip_address_count,
                    'default_for_az': default_for_az,
                    'map_public_ip': map_public_ip,
                    'route_table_id': route_table_id,
                    'vpc_id': vpc.id if vpc else False,
                    'tags': json.dumps(tags_dict) if tags_dict else '',
                    'sync_status': 'synced',
                    'last_sync': fields.Datetime.now(),
                    'sync_message': f'Successfully refreshed subnet data'
                })
                
            else:
                raise UserError(f"Subnet {self.subnet_id} not found in AWS")
                
        except Exception as e:
            error_msg = f"Failed to refresh subnet data: {str(e)}"
            self.write({
                'sync_status': 'error',
                'sync_message': error_msg
            })
            _logger.error(error_msg)

    @api.model
    def import_subnets_from_aws(self, aws_credentials_id=None, region_name=None, vpc_id=None):
        """
        Import subnets from AWS.
        
        Args:
            aws_credentials_id: Optional AWS credentials ID
            region_name: Optional AWS region name
            vpc_id: Optional VPC ID to filter subnets
        
        Returns:
            Action to display imported subnets
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
            
            # Get subnets
            params = {}
            if filters:
                params['Filters'] = filters
            
            response = ec2_client.describe_subnets(**params)
            
            imported_count = 0
            updated_count = 0
            
            for subnet_data in response.get('Subnets', []):
                subnet_id = subnet_data.get('SubnetId')
                
                # Skip if no subnet ID
                if not subnet_id:
                    continue
                
                # Check if subnet already exists
                existing = self.search([('subnet_id', '=', subnet_id)], limit=1)
                
                # Extract details
                state = subnet_data.get('State', 'pending')
                cidr_block = subnet_data.get('CidrBlock', '')
                availability_zone = subnet_data.get('AvailabilityZone', '')
                available_ip_address_count = subnet_data.get('AvailableIpAddressCount', 0)
                default_for_az = subnet_data.get('DefaultForAz', False)
                vpc_id = subnet_data.get('VpcId', '')
                
                # Extract tags
                name = subnet_id
                tags_dict = {}
                
                for tag in ec2_client.describe_tags(
                    Filters=[{'Name': 'resource-id', 'Values': [subnet_id]}]
                ).get('Tags', []):
                    if tag['Key'] == 'Name':
                        name = tag['Value']
                    else:
                        tags_dict[tag['Key']] = tag['Value']
                
                # Get map public IP setting
                map_public_ip = False
                try:
                    map_public_ip_response = ec2_client.describe_subnet_attribute(
                        SubnetId=subnet_id,
                        Attribute='mapPublicIpOnLaunch'
                    )
                    map_public_ip = map_public_ip_response.get('MapPublicIpOnLaunch', {}).get('Value', False)
                except Exception as e:
                    _logger.warning(f"Could not get map public IP setting: {str(e)}")
                
                # Get route table association
                route_table_id = ''
                try:
                    route_tables_response = ec2_client.describe_route_tables(
                        Filters=[{'Name': 'association.subnet-id', 'Values': [subnet_id]}]
                    )
                    if route_tables_response.get('RouteTables'):
                        for route_table in route_tables_response['RouteTables']:
                            for association in route_table.get('Associations', []):
                                if association.get('SubnetId') == subnet_id:
                                    route_table_id = route_table.get('RouteTableId', '')
                                    break
                except Exception as e:
                    _logger.warning(f"Could not get route table association: {str(e)}")
                
                # Get VPC record
                vpc = self.env['aws.ec2.vpc'].search([('vpc_id', '=', vpc_id)], limit=1)
                if not vpc and vpc_id:
                    # Create VPC record if it doesn't exist
                    vpc = self.env['aws.ec2.vpc'].create({
                        'name': vpc_id,
                        'vpc_id': vpc_id,
                        'aws_credentials_id': aws_credentials_id,
                        'aws_region': region_name or self._get_default_region(),
                    })
                    # Trigger import of VPC data
                    vpc.refresh_vpc_data()
                
                # Create or update the subnet record
                if existing:
                    existing.with_context(import_from_aws=True).write({
                        'name': name,
                        'cidr_block': cidr_block,
                        'state': state,
                        'availability_zone': availability_zone,
                        'available_ip_address_count': available_ip_address_count,
                        'default_for_az': default_for_az,
                        'map_public_ip': map_public_ip,
                        'route_table_id': route_table_id,
                        'vpc_id': vpc.id if vpc else False,
                        'tags': json.dumps(tags_dict) if tags_dict else '',
                        'sync_status': 'synced',
                        'last_sync': fields.Datetime.now(),
                        'sync_message': f'Successfully imported from AWS'
                    })
                    updated_count += 1
                else:
                    # Create new subnet record
                    self.with_context(import_from_aws=True).create({
                        'name': name,
                        'subnet_id': subnet_id,
                        'cidr_block': cidr_block,
                        'state': state,
                        'availability_zone': availability_zone,
                        'available_ip_address_count': available_ip_address_count,
                        'default_for_az': default_for_az,
                        'map_public_ip': map_public_ip,
                        'route_table_id': route_table_id,
                        'vpc_id': vpc.id if vpc else False,
                        'tags': json.dumps(tags_dict) if tags_dict else '',
                        'aws_credentials_id': aws_credentials_id,
                        'aws_region': region_name or self._get_default_region(),
                        'sync_status': 'synced',
                        'last_sync': fields.Datetime.now(),
                        'sync_message': f'Successfully imported from AWS'
                    })
                    imported_count += 1
            
            # Show a success message
            message = f"Successfully imported {imported_count} new subnets and updated {updated_count} existing subnets."
            
            # Log the import operation
            self._log_aws_operation('import_subnets', 'success', message)
            
            # Return action to display subnets
            return {
                'name': _('Imported Subnets'),
                'type': 'ir.actions.act_window',
                'res_model': 'aws.ec2.subnet',
                'view_mode': 'tree,form',
                'target': 'current',
                'context': {
                    'default_aws_credentials_id': aws_credentials_id,
                    'default_aws_region': region_name or self._get_default_region(),
                },
                'help': message,
            }
            
        except Exception as e:
            error_msg = f"Failed to import subnets: {str(e)}"
            self._log_aws_operation('import_subnets', 'error', error_msg)
            raise UserError(error_msg)

    def refresh_all_subnets(self):
        """
        Refresh all active subnets.
        """
        subnets = self.search([('active', '=', True), ('subnet_id', '!=', False)])
        for subnet in subnets:
            try:
                subnet.refresh_subnet_data()
            except Exception as e:
                _logger.error(f"Failed to refresh subnet {subnet.subnet_id}: {str(e)}")
        
        # Return a notification message
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Subnet Refresh'),
                'message': _('Refreshed %s subnets.') % len(subnets),
                'sticky': False,
                'type': 'success',
            }
        }