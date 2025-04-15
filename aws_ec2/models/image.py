# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
#
# Copyright (C) 2023 JAAH

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import json
import logging

_logger = logging.getLogger(__name__)

class EC2Image(models.Model):
    """
    Represents an AWS EC2 AMI (Amazon Machine Image).
    """
    _name = 'aws.ec2.image'
    _description = 'EC2 Image (AMI)'
    _inherit = ['aws.service.implementation.mixin', 'aws.service.logger']
    _rec_name = 'name'
    _order = 'name'

    # AMI Identifiers
    name = fields.Char(string='Name', index=True,
                      help='Name of the AMI (tag:Name).')
    image_id = fields.Char(string='Image ID', required=True, index=True,
                          help='The unique ID of the AMI (e.g. ami-0123456789abcdef0).')
    description = fields.Text(string='Description',
                             help='Description of the AMI.')
    
    # AMI Details
    state = fields.Selection([
        ('pending', 'Pending'),
        ('available', 'Available'),
        ('invalid', 'Invalid'),
        ('deregistered', 'Deregistered'),
        ('transient', 'Transient'),
        ('failed', 'Failed'),
        ('error', 'Error')
    ], string='State', readonly=True, default='pending',
    help='Current state of the AMI.')
    
    architecture = fields.Selection([
        ('i386', 'i386'),
        ('x86_64', 'x86_64'),
        ('arm64', 'arm64'),
        ('x86_64_mac', 'x86_64_mac'),
        ('arm64_mac', 'arm64_mac')
    ], string='Architecture', readonly=True,
    help='Architecture of the AMI.')
    
    virtualization_type = fields.Selection([
        ('hvm', 'HVM'),
        ('paravirtual', 'Paravirtual')
    ], string='Virtualization Type', readonly=True,
    help='Virtualization type of the AMI.')
    
    root_device_type = fields.Selection([
        ('ebs', 'EBS'),
        ('instance-store', 'Instance Store')
    ], string='Root Device Type', readonly=True,
    help='Type of root device used by the AMI.')
    
    root_device_name = fields.Char(string='Root Device Name', readonly=True,
                                  help='Name of the root device (e.g. /dev/sda1).')
    
    # Ownership and Permissions
    owner_id = fields.Char(string='Owner ID', readonly=True,
                          help='AWS account ID of the AMI owner.')
    is_public = fields.Boolean(string='Public', readonly=True, default=False,
                              help='Whether the AMI is publicly available.')
    
    # Creation and Platform
    creation_date = fields.Datetime(string='Creation Date', readonly=True,
                                   help='When the AMI was created.')
    platform = fields.Selection([
        ('windows', 'Windows'),
        ('linux', 'Linux/Unix')
    ], string='Platform', readonly=True,
    help='Platform of the AMI.')
    
    # Size and Storage
    image_size = fields.Float(string='Size (GB)', readonly=True,
                             help='Size of the AMI in GB.')
    block_device_mappings = fields.Text(string='Block Device Mappings', readonly=True,
                                       help='JSON representation of the block device mappings.')
    
    # Tags and Metadata
    tags = fields.Text(string='Tags', 
                      help='JSON representation of the AMI tags.')
    
    # Usage Information
    instance_ids = fields.One2many('aws.ec2.instance', 'image_id', string='Instances Using This AMI',
                                  compute='_compute_instances')
    instance_count = fields.Integer(string='Instance Count', compute='_compute_instances',
                                   help='Number of instances using this AMI.')
    
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

    def _compute_instances(self):
        """
        Compute the instances using this AMI.
        """
        for image in self:
            instances = self.env['aws.ec2.instance'].search([
                ('image_id', '=', image.image_id)
            ])
            image.instance_ids = instances
            image.instance_count = len(instances)

    @api.model
    def create(self, vals):
        """
        Create a new AMI record in Odoo.
        Note: This doesn't create a new AMI in AWS, only imports existing ones.
        """
        return super(EC2Image, self).create(vals)

    def _refresh_image_data(self):
        """
        Refresh image data from AWS.
        """
        self.ensure_one()
        
        if not self.image_id:
            return
        
        try:
            ec2_client = self._get_boto3_client('ec2')
            
            # Get image details
            response = ec2_client.describe_images(ImageIds=[self.image_id])
            
            if 'Images' in response and response['Images']:
                image_data = response['Images'][0]
                
                # Extract details
                name = self.image_id
                description = ''
                tags_dict = {}
                
                # Extract name and tags
                if 'Tags' in image_data:
                    for tag in image_data.get('Tags', []):
                        if tag.get('Key') == 'Name':
                            name = tag.get('Value', self.image_id)
                        else:
                            tags_dict[tag.get('Key')] = tag.get('Value')
                
                # Get description
                description = image_data.get('Description', '')
                
                # Parse creation date if available
                creation_date = False
                if 'CreationDate' in image_data:
                    creation_date = fields.Datetime.from_string(image_data['CreationDate'])
                
                # Extract block device mappings
                block_device_mappings = json.dumps(image_data.get('BlockDeviceMappings', []))
                
                # Determine platform
                platform = 'linux'
                if image_data.get('Platform') == 'windows':
                    platform = 'windows'
                
                # Calculate image size if available
                image_size = 0
                for mapping in image_data.get('BlockDeviceMappings', []):
                    if 'Ebs' in mapping and 'VolumeSize' in mapping['Ebs']:
                        image_size += mapping['Ebs']['VolumeSize']
                
                # Update the record
                self.with_context(import_from_aws=True).write({
                    'name': name,
                    'description': description,
                    'state': image_data.get('State', 'unknown'),
                    'architecture': image_data.get('Architecture', False),
                    'virtualization_type': image_data.get('VirtualizationType', False),
                    'root_device_type': image_data.get('RootDeviceType', False),
                    'root_device_name': image_data.get('RootDeviceName', ''),
                    'owner_id': image_data.get('OwnerId', ''),
                    'is_public': image_data.get('Public', False),
                    'creation_date': creation_date,
                    'platform': platform,
                    'image_size': image_size,
                    'block_device_mappings': block_device_mappings,
                    'tags': json.dumps(tags_dict) if tags_dict else '',
                    'sync_status': 'synced',
                    'last_sync': fields.Datetime.now(),
                    'sync_message': f'Successfully refreshed AMI data'
                })
                
            else:
                raise UserError(f"AMI {self.image_id} not found in AWS")
                
        except Exception as e:
            error_msg = f"Failed to refresh AMI data: {str(e)}"
            self.write({
                'sync_status': 'error',
                'sync_message': error_msg
            })
            _logger.error(error_msg)

    def create_image_from_instance(self, instance_id, name, description=None, no_reboot=True, tags=None):
        """
        Create a new AMI from an existing EC2 instance.
        
        Args:
            instance_id: EC2 instance ID to create image from
            name: Name for the new image
            description: Optional description for the new image
            no_reboot: If True, do not reboot the instance before creating the image
            tags: Optional tags for the new image
        
        Returns:
            New image record
        """
        try:
            ec2_client = self._get_boto3_client('ec2')
            
            # Prepare parameters
            params = {
                'InstanceId': instance_id,
                'Name': name,
                'NoReboot': no_reboot
            }
            
            if description:
                params['Description'] = description
            
            # Create the image
            response = ec2_client.create_image(**params)
            
            if 'ImageId' in response:
                image_id = response['ImageId']
                
                # Add tags if provided
                if tags:
                    try:
                        tags_list = []
                        tags_dict = json.loads(tags) if isinstance(tags, str) else tags
                        for key, value in tags_dict.items():
                            tags_list.append({'Key': key, 'Value': str(value)})
                        
                        # Add name tag if not in custom tags
                        if not any(tag.get('Key') == 'Name' for tag in tags_list):
                            tags_list.append({'Key': 'Name', 'Value': name})
                        
                        if tags_list:
                            ec2_client.create_tags(
                                Resources=[image_id],
                                Tags=tags_list
                            )
                    except Exception as e:
                        _logger.warning(f"Could not add tags to AMI: {str(e)}")
                
                # Create a new image record
                new_image = self.create({
                    'name': name,
                    'image_id': image_id,
                    'description': description or '',
                    'tags': tags if isinstance(tags, str) else json.dumps(tags) if tags else '',
                    'aws_credentials_id': self._get_aws_credentials_id(),
                    'aws_region': self._get_aws_region(),
                    'state': 'pending',
                    'sync_status': 'synced',
                    'last_sync': fields.Datetime.now(),
                    'sync_message': f'Successfully created AMI {image_id}'
                })
                
                # Log the success
                self._log_aws_operation('create_image', 'success', 
                                       f"Successfully created AMI {image_id} from instance {instance_id}")
                
                return new_image
            else:
                raise UserError("Failed to create AMI: No image ID in response")
                
        except Exception as e:
            error_msg = f"Failed to create AMI: {str(e)}"
            self._log_aws_operation('create_image', 'error', error_msg)
            raise UserError(error_msg)

    def deregister_image(self):
        """
        Deregister (delete) an AMI from AWS.
        """
        self.ensure_one()
        
        if not self.image_id:
            return
        
        try:
            # Check if the image is being used by instances
            if self.instance_count > 0:
                raise UserError(f"Cannot deregister AMI '{self.name}' ({self.image_id}) as it is still being used by {self.instance_count} instances.")
            
            ec2_client = self._get_boto3_client('ec2')
            
            # Deregister the image
            ec2_client.deregister_image(ImageId=self.image_id)
            
            # Update the record
            self.write({
                'state': 'deregistered',
                'sync_status': 'synced',
                'last_sync': fields.Datetime.now(),
                'sync_message': f'Successfully deregistered AMI {self.image_id}'
            })
            
            # Log the success
            self._log_aws_operation('deregister_image', 'success', 
                                   f"Successfully deregistered AMI {self.image_id}")
            
        except Exception as e:
            error_msg = f"Failed to deregister AMI {self.image_id}: {str(e)}"
            self.write({
                'sync_status': 'error',
                'sync_message': error_msg
            })
            self._log_aws_operation('deregister_image', 'error', error_msg)
            raise UserError(error_msg)
    
    def modify_image_attribute(self, attribute, value):
        """
        Modify an attribute of an AMI.
        
        Args:
            attribute: Attribute to modify (e.g. 'description', 'launchPermission')
            value: New value for the attribute
        """
        self.ensure_one()
        
        if not self.image_id:
            return
        
        try:
            ec2_client = self._get_boto3_client('ec2')
            
            if attribute == 'description':
                # Modify description
                ec2_client.modify_image_attribute(
                    ImageId=self.image_id,
                    Description={'Value': value}
                )
                
                # Update the record
                self.write({
                    'description': value,
                    'sync_status': 'synced',
                    'last_sync': fields.Datetime.now(),
                    'sync_message': f'Successfully updated AMI description'
                })
                
            elif attribute == 'launchPermission':
                # Modify launch permission (make public or private)
                if value == 'public':
                    ec2_client.modify_image_attribute(
                        ImageId=self.image_id,
                        LaunchPermission={
                            'Add': [{'Group': 'all'}]
                        }
                    )
                    
                    # Update the record
                    self.write({
                        'is_public': True,
                        'sync_status': 'synced',
                        'last_sync': fields.Datetime.now(),
                        'sync_message': f'Successfully made AMI public'
                    })
                    
                elif value == 'private':
                    ec2_client.modify_image_attribute(
                        ImageId=self.image_id,
                        LaunchPermission={
                            'Remove': [{'Group': 'all'}]
                        }
                    )
                    
                    # Update the record
                    self.write({
                        'is_public': False,
                        'sync_status': 'synced',
                        'last_sync': fields.Datetime.now(),
                        'sync_message': f'Successfully made AMI private'
                    })
            
            # Log the success
            self._log_aws_operation('modify_image_attribute', 'success', 
                                   f"Successfully modified AMI {self.image_id} attribute: {attribute}")
            
        except Exception as e:
            error_msg = f"Failed to modify AMI {self.image_id} attribute: {str(e)}"
            self.write({
                'sync_status': 'error',
                'sync_message': error_msg
            })
            self._log_aws_operation('modify_image_attribute', 'error', error_msg)
            raise UserError(error_msg)

    @api.model
    def import_images_from_aws(self, aws_credentials_id=None, region_name=None, owner_id='self', filters=None):
        """
        Import AMIs from AWS.
        
        Args:
            aws_credentials_id: Optional AWS credentials ID
            region_name: Optional AWS region name
            owner_id: AMI owner filter (default: 'self' for your own AMIs)
            filters: Additional filters for the AMIs
        
        Returns:
            Action to display imported AMIs
        """
        try:
            # Use provided credentials or default from context
            if not aws_credentials_id:
                aws_credentials_id = self.env.context.get('aws_credentials_id', False)
            
            if not region_name:
                region_name = self.env.context.get('aws_region', False)
            
            ec2_client = self._get_boto3_client('ec2', aws_credentials_id, region_name)
            
            # Prepare parameters
            params = {}
            
            if owner_id:
                if owner_id == 'self':
                    params['Owners'] = ['self']
                else:
                    params['Owners'] = [owner_id]
            
            if filters:
                params['Filters'] = filters
            
            # Get all AMIs
            response = ec2_client.describe_images(**params)
            
            imported_count = 0
            updated_count = 0
            
            for image_data in response.get('Images', []):
                image_id = image_data.get('ImageId')
                
                # Skip if no image ID
                if not image_id:
                    continue
                
                # Check if image already exists
                existing = self.search([('image_id', '=', image_id)], limit=1)
                
                # Extract name and description
                name = image_id
                description = image_data.get('Description', '')
                tags_dict = {}
                
                if 'Tags' in image_data:
                    for tag in image_data.get('Tags', []):
                        if tag.get('Key') == 'Name':
                            name = tag.get('Value', image_id)
                        else:
                            tags_dict[tag.get('Key')] = tag.get('Value')
                
                # Parse creation date if available
                creation_date = False
                if 'CreationDate' in image_data:
                    creation_date = fields.Datetime.from_string(image_data['CreationDate'])
                
                # Extract block device mappings
                block_device_mappings = json.dumps(image_data.get('BlockDeviceMappings', []))
                
                # Determine platform
                platform = 'linux'
                if image_data.get('Platform') == 'windows':
                    platform = 'windows'
                
                # Calculate image size if available
                image_size = 0
                for mapping in image_data.get('BlockDeviceMappings', []):
                    if 'Ebs' in mapping and 'VolumeSize' in mapping['Ebs']:
                        image_size += mapping['Ebs']['VolumeSize']
                
                # Create or update the image record
                if existing:
                    existing.with_context(import_from_aws=True).write({
                        'name': name,
                        'description': description,
                        'state': image_data.get('State', 'unknown'),
                        'architecture': image_data.get('Architecture', False),
                        'virtualization_type': image_data.get('VirtualizationType', False),
                        'root_device_type': image_data.get('RootDeviceType', False),
                        'root_device_name': image_data.get('RootDeviceName', ''),
                        'owner_id': image_data.get('OwnerId', ''),
                        'is_public': image_data.get('Public', False),
                        'creation_date': creation_date,
                        'platform': platform,
                        'image_size': image_size,
                        'block_device_mappings': block_device_mappings,
                        'tags': json.dumps(tags_dict) if tags_dict else '',
                        'sync_status': 'synced',
                        'last_sync': fields.Datetime.now(),
                        'sync_message': f'Successfully imported from AWS'
                    })
                    updated_count += 1
                else:
                    # Create new image record
                    self.with_context(import_from_aws=True).create({
                        'name': name,
                        'image_id': image_id,
                        'description': description,
                        'state': image_data.get('State', 'unknown'),
                        'architecture': image_data.get('Architecture', False),
                        'virtualization_type': image_data.get('VirtualizationType', False),
                        'root_device_type': image_data.get('RootDeviceType', False),
                        'root_device_name': image_data.get('RootDeviceName', ''),
                        'owner_id': image_data.get('OwnerId', ''),
                        'is_public': image_data.get('Public', False),
                        'creation_date': creation_date,
                        'platform': platform,
                        'image_size': image_size,
                        'block_device_mappings': block_device_mappings,
                        'tags': json.dumps(tags_dict) if tags_dict else '',
                        'aws_credentials_id': aws_credentials_id,
                        'aws_region': region_name or self._get_default_region(),
                        'sync_status': 'synced',
                        'last_sync': fields.Datetime.now(),
                        'sync_message': f'Successfully imported from AWS'
                    })
                    imported_count += 1
            
            # Show a success message
            message = f"Successfully imported {imported_count} new AMIs and updated {updated_count} existing AMIs."
            
            # Log the import operation
            self._log_aws_operation('import_images', 'success', message)
            
            # Return action to display AMIs
            return {
                'name': _('Imported AMIs'),
                'type': 'ir.actions.act_window',
                'res_model': 'aws.ec2.image',
                'view_mode': 'tree,form',
                'target': 'current',
                'context': {
                    'default_aws_credentials_id': aws_credentials_id,
                    'default_aws_region': region_name or self._get_default_region(),
                },
                'help': message,
            }
            
        except Exception as e:
            error_msg = f"Failed to import AMIs: {str(e)}"
            self._log_aws_operation('import_images', 'error', error_msg)
            raise UserError(error_msg)

    def refresh_all_images(self):
        """
        Refresh all active AMIs.
        """
        images = self.search([('active', '=', True), ('image_id', '!=', False)])
        for image in images:
            try:
                image._refresh_image_data()
            except Exception as e:
                _logger.error(f"Failed to refresh AMI {image.image_id}: {str(e)}")
        
        # Return a notification message
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('AMI Refresh'),
                'message': _('Refreshed %s AMIs.') % len(images),
                'sticky': False,
                'type': 'success',
            }
        }