# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
#
# Copyright (C) 2023 JAAH

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import base64
import logging
import json

_logger = logging.getLogger(__name__)

class EC2KeyPair(models.Model):
    """
    Represents an AWS EC2 key pair.
    """
    _name = 'aws.ec2.key.pair'
    _description = 'EC2 Key Pair'
    _inherit = ['aws.service.implementation.mixin', 'aws.service.logger']
    _rec_name = 'key_name'
    _order = 'key_name'

    # Key Pair Details
    key_name = fields.Char(string='Key Name', required=True, index=True,
                          help='Name of the key pair.')
    key_fingerprint = fields.Char(string='Key Fingerprint', readonly=True,
                                 help='The SHA1 digest of the DER encoded private key.')
    key_material = fields.Text(string='Private Key Material', readonly=True,
                              help='The private key material (only available when creating a new key pair).')
    
    # Key Type
    key_type = fields.Selection([
        ('rsa', 'RSA'),
        ('ed25519', 'ED25519')
    ], string='Key Type', default='rsa',
    help='The type of key pair to create.')
    
    # Attachment for stored key file
    key_file = fields.Binary(string='Key File (.pem)', attachment=True,
                            help='The .pem file for this key pair.')
    key_filename = fields.Char(string='Key Filename', readonly=True,
                              help='The filename of the .pem key file.')
    
    # Tags and Metadata
    tags = fields.Text(string='Tags', 
                      help='JSON representation of the key pair tags.')
    
    # Usage Information
    instance_ids = fields.One2many('aws.ec2.instance', 'key_pair_id', string='Associated Instances',
                                  help='Instances using this key pair.')
    instance_count = fields.Integer(string='Instance Count', compute='_compute_instance_count',
                                   help='Number of instances using this key pair.')
    
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

    def _compute_instance_count(self):
        """
        Compute the number of instances using this key pair.
        """
        for key_pair in self:
            key_pair.instance_count = len(key_pair.instance_ids)

    @api.model
    def create(self, vals):
        """
        Create a new key pair both in Odoo and AWS.
        """
        key_pair = super(EC2KeyPair, self).create(vals)
        if not self.env.context.get('import_from_aws', False):
            try:
                key_pair._create_key_pair_in_aws()
            except Exception as e:
                key_pair.write({
                    'sync_status': 'error',
                    'sync_message': str(e),
                })
                _logger.error(f"Failed to create key pair: {str(e)}")
                raise UserError(f"Failed to create key pair: {str(e)}")
        return key_pair

    def unlink(self):
        """
        Delete the key pair from AWS before removing from Odoo.
        """
        for key_pair in self:
            try:
                if key_pair.key_name:
                    # Check if the key pair is still in use
                    if key_pair.instance_count > 0:
                        raise UserError(f"Cannot delete key pair '{key_pair.key_name}' as it is still being used by {key_pair.instance_count} instances.")
                    
                    key_pair._delete_key_pair_from_aws()
            except Exception as e:
                _logger.error(f"Failed to delete key pair {key_pair.key_name}: {str(e)}")
                raise UserError(f"Failed to delete key pair: {str(e)}")
        return super(EC2KeyPair, self).unlink()

    def _create_key_pair_in_aws(self):
        """
        Create a new key pair in AWS.
        """
        self.ensure_one()
        self.write({'sync_status': 'syncing'})
        
        # Initialize boto3 client
        ec2_client = self._get_boto3_client('ec2')
        
        try:
            # Create the key pair
            if self.key_type == 'ed25519':
                response = ec2_client.create_key_pair(
                    KeyName=self.key_name,
                    KeyType='ed25519',
                    TagSpecifications=[
                        {
                            'ResourceType': 'key-pair',
                            'Tags': [{'Key': 'Name', 'Value': self.key_name}]
                        }
                    ]
                )
            else:  # Default to RSA
                response = ec2_client.create_key_pair(
                    KeyName=self.key_name,
                    KeyType='rsa',
                    TagSpecifications=[
                        {
                            'ResourceType': 'key-pair',
                            'Tags': [{'Key': 'Name', 'Value': self.key_name}]
                        }
                    ]
                )
            
            # Extract key details from response
            key_fingerprint = response.get('KeyFingerprint', '')
            key_material = response.get('KeyMaterial', '')
            
            # Add custom tags if provided
            if self.tags:
                try:
                    tags_list = []
                    tags_dict = json.loads(self.tags)
                    for key, value in tags_dict.items():
                        tags_list.append({'Key': key, 'Value': str(value)})
                    
                    if tags_list:
                        ec2_client.create_tags(
                            Resources=[self.key_name],
                            Tags=tags_list
                        )
                except Exception as e:
                    _logger.warning(f"Could not add tags to key pair: {str(e)}")
            
            # Generate a .pem file
            key_filename = f"{self.key_name}.pem"
            key_file = base64.b64encode(key_material.encode('utf-8'))
            
            # Update the record with key details
            self.write({
                'key_fingerprint': key_fingerprint,
                'key_material': key_material,  # Store temporarily
                'key_file': key_file,
                'key_filename': key_filename,
                'sync_status': 'synced',
                'last_sync': fields.Datetime.now(),
                'sync_message': f'Successfully created key pair {self.key_name}'
            })
            
            # Log the success
            self._log_aws_operation('create_key_pair', 'success', 
                                   f"Successfully created key pair {self.key_name}")
            
            # Clear key material after saving to attachment (for security)
            self.write({'key_material': False})
            
        except Exception as e:
            error_msg = f"Failed to create key pair: {str(e)}"
            self.write({
                'sync_status': 'error',
                'sync_message': error_msg
            })
            self._log_aws_operation('create_key_pair', 'error', error_msg)
            raise UserError(error_msg)

    def _delete_key_pair_from_aws(self):
        """
        Delete a key pair from AWS.
        """
        self.ensure_one()
        
        if not self.key_name:
            return
        
        try:
            ec2_client = self._get_boto3_client('ec2')
            
            # Delete the key pair
            ec2_client.delete_key_pair(KeyName=self.key_name)
            
            # Log the success
            self._log_aws_operation('delete_key_pair', 'success', 
                                   f"Successfully deleted key pair {self.key_name}")
            
        except Exception as e:
            error_msg = f"Failed to delete key pair {self.key_name}: {str(e)}"
            self._log_aws_operation('delete_key_pair', 'error', error_msg)
            raise UserError(error_msg)

    def download_key_file(self):
        """
        Generate a download action for the key file.
        """
        self.ensure_one()
        
        if not self.key_file:
            raise UserError("No key file available for download.")
        
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content?model={self._name}&id={self.id}&field=key_file&filename={self.key_filename}&download=true',
            'target': 'self',
        }

    @api.model
    def import_key_pairs_from_aws(self, aws_credentials_id=None, region_name=None):
        """
        Import key pairs from AWS.
        
        Args:
            aws_credentials_id: Optional AWS credentials ID
            region_name: Optional AWS region name
        
        Returns:
            Action to display imported key pairs
        """
        try:
            # Use provided credentials or default from context
            if not aws_credentials_id:
                aws_credentials_id = self.env.context.get('aws_credentials_id', False)
            
            if not region_name:
                region_name = self.env.context.get('aws_region', False)
            
            ec2_client = self._get_boto3_client('ec2', aws_credentials_id, region_name)
            
            # Get all key pairs
            response = ec2_client.describe_key_pairs()
            
            imported_count = 0
            updated_count = 0
            
            for key_data in response.get('KeyPairs', []):
                key_name = key_data.get('KeyName')
                
                # Skip if no key name
                if not key_name:
                    continue
                
                # Check if key pair already exists
                existing = self.search([('key_name', '=', key_name)], limit=1)
                
                # Extract key pair details
                key_fingerprint = key_data.get('KeyFingerprint', '')
                key_type = key_data.get('KeyType', 'rsa').lower()
                
                # Create or update the key pair
                if existing:
                    existing.with_context(import_from_aws=True).write({
                        'key_fingerprint': key_fingerprint,
                        'key_type': key_type,
                        'sync_status': 'synced',
                        'last_sync': fields.Datetime.now(),
                        'sync_message': f'Successfully imported from AWS'
                    })
                    updated_count += 1
                else:
                    # Create new key pair record
                    self.with_context(import_from_aws=True).create({
                        'key_name': key_name,
                        'key_fingerprint': key_fingerprint,
                        'key_type': key_type,
                        'aws_credentials_id': aws_credentials_id,
                        'aws_region': region_name or self._get_default_region(),
                        'sync_status': 'synced',
                        'last_sync': fields.Datetime.now(),
                        'sync_message': f'Successfully imported from AWS'
                    })
                    imported_count += 1
            
            # Show a success message
            message = f"Successfully imported {imported_count} new key pairs and updated {updated_count} existing key pairs."
            
            # Log the import operation
            self._log_aws_operation('import_key_pairs', 'success', message)
            
            # Return action to display key pairs
            return {
                'name': _('Imported Key Pairs'),
                'type': 'ir.actions.act_window',
                'res_model': 'aws.ec2.key.pair',
                'view_mode': 'tree,form',
                'target': 'current',
                'context': {
                    'default_aws_credentials_id': aws_credentials_id,
                    'default_aws_region': region_name or self._get_default_region(),
                },
                'help': message,
            }
            
        except Exception as e:
            error_msg = f"Failed to import key pairs: {str(e)}"
            self._log_aws_operation('import_key_pairs', 'error', error_msg)
            raise UserError(error_msg)