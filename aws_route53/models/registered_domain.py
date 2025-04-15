# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
#
# Copyright (C) 2023 JAAH

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import json
import logging
import datetime

_logger = logging.getLogger(__name__)

class Route53RegisteredDomain(models.Model):
    """
    Represents a domain registered through AWS Route 53 Domains.
    """
    _name = 'aws.route53.registered.domain'
    _description = 'Route 53 Registered Domain'
    _inherit = ['aws.service.implementation.mixin', 'aws.service.logger']
    _rec_name = 'domain_name'
    _order = 'domain_name'

    # Domain Identifiers
    domain_name = fields.Char(string='Domain Name', required=True, index=True,
                             help='The registered domain name (e.g. example.com)')
    
    # Registration Status
    status = fields.Selection([
        ('registered', 'Registered'),
        ('pending', 'Pending'),
        ('expired', 'Expired'),
        ('pending_transfer', 'Pending Transfer'),
        ('redemption_period', 'Redemption Period'),
        ('auto_renewing', 'Auto Renewing'),
        ('pending_delete', 'Pending Delete'),
        ('transferring_away', 'Transferring Away'),
        ('unknown', 'Unknown')
    ], string='Status', default='unknown',
    help='Current status of the domain registration')
    
    # Registration Dates
    expiration_date = fields.Datetime(string='Expiration Date',
                                     help='When the domain registration expires')
    updated_date = fields.Datetime(string='Updated Date',
                                  help='When the domain was last updated')
    registration_date = fields.Datetime(string='Registration Date',
                                       help='When the domain was registered')
    
    # Auto-renewal Settings
    auto_renew = fields.Boolean(string='Auto Renew', default=True,
                               help='Whether the domain will be automatically renewed')
    transfer_lock = fields.Boolean(string='Transfer Lock', default=True,
                                  help='Whether the domain is locked to prevent unauthorized transfers')
    
    # Contact Information
    admin_contact = fields.Text(string='Admin Contact',
                               help='JSON representation of the admin contact information')
    registrant_contact = fields.Text(string='Registrant Contact',
                                    help='JSON representation of the registrant contact information')
    tech_contact = fields.Text(string='Technical Contact',
                              help='JSON representation of the technical contact information')
    
    # Privacy Protection
    admin_privacy = fields.Boolean(string='Admin Privacy', default=True,
                                  help='Whether contact information privacy is enabled for admin contact')
    registrant_privacy = fields.Boolean(string='Registrant Privacy', default=True,
                                       help='Whether contact information privacy is enabled for registrant contact')
    tech_privacy = fields.Boolean(string='Technical Privacy', default=True,
                                 help='Whether contact information privacy is enabled for technical contact')
    
    # Name Servers
    name_servers = fields.Text(string='Name Servers',
                              help='List of name servers for this domain')
    
    # Related Resources
    hosted_zone_id = fields.Many2one('aws.route53.hosted.zone', string='Hosted Zone',
                                     help='The Route 53 hosted zone for this domain')
    
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

    _sql_constraints = [
        ('domain_name_unique', 'UNIQUE(domain_name)', 'Domain name must be unique!')
    ]

    def refresh_domain_data(self):
        """
        Refresh domain registration data from AWS.
        """
        self.ensure_one()
        
        if not self.domain_name:
            return
        
        try:
            # Initialize boto3 client for Route 53 Domains
            r53domains_client = self._get_boto3_client('route53domains')
            
            # Get domain details
            response = r53domains_client.get_domain_detail(
                DomainName=self.domain_name
            )
            
            # Extract status
            status = 'unknown'
            if 'Status' in response:
                aws_status = response['Status']
                if aws_status in ['registered', 'pending', 'pendingTransfer', 'expired',
                                 'redemptionPeriod', 'autoRenewing', 'pendingDelete',
                                 'transferringAway']:
                    status = aws_status.lower()
                    if status == 'pendingtransfer':
                        status = 'pending_transfer'
                    elif status == 'redemptionperiod':
                        status = 'redemption_period'
                    elif status == 'autorenewing':
                        status = 'auto_renewing'
                    elif status == 'pendingdelete':
                        status = 'pending_delete'
                    elif status == 'transferringaway':
                        status = 'transferring_away'
            
            # Extract dates
            expiration_date = False
            if 'ExpirationDate' in response:
                expiration_date = response['ExpirationDate']
            
            updated_date = False
            if 'UpdatedDate' in response:
                updated_date = response['UpdatedDate']
            
            registration_date = False
            if 'CreationDate' in response:
                registration_date = response['CreationDate']
            
            # Extract settings
            auto_renew = False
            if 'AutoRenew' in response:
                auto_renew = response['AutoRenew']
            
            transfer_lock = False
            if 'TransferLock' in response:
                transfer_lock = response['TransferLock']
            
            # Extract contact information
            admin_contact = {}
            if 'AdminContact' in response:
                admin_contact = response['AdminContact']
            
            registrant_contact = {}
            if 'RegistrantContact' in response:
                registrant_contact = response['RegistrantContact']
            
            tech_contact = {}
            if 'TechContact' in response:
                tech_contact = response['TechContact']
            
            # Extract privacy settings
            admin_privacy = False
            if 'AdminPrivacy' in response:
                admin_privacy = response['AdminPrivacy']
            
            registrant_privacy = False
            if 'RegistrantPrivacy' in response:
                registrant_privacy = response['RegistrantPrivacy']
            
            tech_privacy = False
            if 'TechPrivacy' in response:
                tech_privacy = response['TechPrivacy']
            
            # Extract name servers
            name_servers = []
            if 'Nameservers' in response:
                name_servers = response['Nameservers']
            
            # Update the record
            self.write({
                'status': status,
                'expiration_date': expiration_date,
                'updated_date': updated_date,
                'registration_date': registration_date,
                'auto_renew': auto_renew,
                'transfer_lock': transfer_lock,
                'admin_contact': json.dumps(admin_contact) if admin_contact else '',
                'registrant_contact': json.dumps(registrant_contact) if registrant_contact else '',
                'tech_contact': json.dumps(tech_contact) if tech_contact else '',
                'admin_privacy': admin_privacy,
                'registrant_privacy': registrant_privacy,
                'tech_privacy': tech_privacy,
                'name_servers': json.dumps(name_servers) if name_servers else '',
                'sync_status': 'synced',
                'last_sync': fields.Datetime.now(),
                'sync_message': f'Successfully refreshed domain data'
            })
            
            # Look for a matching hosted zone
            if not self.hosted_zone_id:
                hosted_zone = self.env['aws.route53.hosted.zone'].search([
                    ('domain_name', '=', self.domain_name)
                ], limit=1)
                if hosted_zone:
                    self.hosted_zone_id = hosted_zone.id
            
        except Exception as e:
            error_msg = f"Failed to refresh domain data: {str(e)}"
            self.write({
                'sync_status': 'error',
                'sync_message': error_msg
            })
            _logger.error(error_msg)
    
    def update_auto_renew(self, enable):
        """
        Enable or disable auto-renewal for the domain.
        
        Args:
            enable: Boolean indicating whether to enable auto-renewal
        """
        self.ensure_one()
        
        if not self.domain_name:
            return
        
        try:
            # Initialize boto3 client for Route 53 Domains
            r53domains_client = self._get_boto3_client('route53domains')
            
            # Update auto-renewal setting
            r53domains_client.update_domain_contact(
                DomainName=self.domain_name,
                AdminContact=json.loads(self.admin_contact) if self.admin_contact else None,
                RegistrantContact=json.loads(self.registrant_contact) if self.registrant_contact else None,
                TechContact=json.loads(self.tech_contact) if self.tech_contact else None
            )
            
            r53domains_client.enable_domain_auto_renew(
                DomainName=self.domain_name
            ) if enable else r53domains_client.disable_domain_auto_renew(
                DomainName=self.domain_name
            )
            
            # Update the record
            self.write({
                'auto_renew': enable,
                'sync_status': 'synced',
                'last_sync': fields.Datetime.now(),
                'sync_message': f"Successfully {'enabled' if enable else 'disabled'} auto-renewal"
            })
            
            # Log the action
            self._log_aws_operation('update_auto_renew', 'success', 
                                   f"Successfully {'enabled' if enable else 'disabled'} auto-renewal for {self.domain_name}")
            
        except Exception as e:
            error_msg = f"Failed to update auto-renewal: {str(e)}"
            self.write({
                'sync_status': 'error',
                'sync_message': error_msg
            })
            self._log_aws_operation('update_auto_renew', 'error', error_msg)
            raise UserError(error_msg)
    
    def update_transfer_lock(self, enable):
        """
        Enable or disable transfer lock for the domain.
        
        Args:
            enable: Boolean indicating whether to enable transfer lock
        """
        self.ensure_one()
        
        if not self.domain_name:
            return
        
        try:
            # Initialize boto3 client for Route 53 Domains
            r53domains_client = self._get_boto3_client('route53domains')
            
            # Update transfer lock setting
            r53domains_client.enable_domain_transfer_lock(
                DomainName=self.domain_name
            ) if enable else r53domains_client.disable_domain_transfer_lock(
                DomainName=self.domain_name
            )
            
            # Update the record
            self.write({
                'transfer_lock': enable,
                'sync_status': 'synced',
                'last_sync': fields.Datetime.now(),
                'sync_message': f"Successfully {'enabled' if enable else 'disabled'} transfer lock"
            })
            
            # Log the action
            self._log_aws_operation('update_transfer_lock', 'success', 
                                   f"Successfully {'enabled' if enable else 'disabled'} transfer lock for {self.domain_name}")
            
        except Exception as e:
            error_msg = f"Failed to update transfer lock: {str(e)}"
            self.write({
                'sync_status': 'error',
                'sync_message': error_msg
            })
            self._log_aws_operation('update_transfer_lock', 'error', error_msg)
            raise UserError(error_msg)
    
    def update_contact_privacy(self, admin=None, registrant=None, tech=None):
        """
        Update privacy protection settings for domain contacts.
        
        Args:
            admin: Boolean indicating whether to enable privacy for admin contact
            registrant: Boolean indicating whether to enable privacy for registrant contact
            tech: Boolean indicating whether to enable privacy for technical contact
        """
        self.ensure_one()
        
        if not self.domain_name:
            return
        
        try:
            # Initialize boto3 client for Route 53 Domains
            r53domains_client = self._get_boto3_client('route53domains')
            
            # Prepare parameters
            params = {
                'DomainName': self.domain_name,
            }
            
            if admin is not None:
                params['AdminPrivacy'] = admin
            
            if registrant is not None:
                params['RegistrantPrivacy'] = registrant
            
            if tech is not None:
                params['TechPrivacy'] = tech
            
            # Update privacy settings
            r53domains_client.update_domain_contact_privacy(**params)
            
            # Prepare update values for Odoo record
            update_vals = {
                'sync_status': 'synced',
                'last_sync': fields.Datetime.now(),
                'sync_message': 'Successfully updated privacy settings'
            }
            
            if admin is not None:
                update_vals['admin_privacy'] = admin
            
            if registrant is not None:
                update_vals['registrant_privacy'] = registrant
            
            if tech is not None:
                update_vals['tech_privacy'] = tech
            
            # Update the record
            self.write(update_vals)
            
            # Log the action
            self._log_aws_operation('update_contact_privacy', 'success', 
                                   f"Successfully updated privacy settings for {self.domain_name}")
            
        except Exception as e:
            error_msg = f"Failed to update privacy settings: {str(e)}"
            self.write({
                'sync_status': 'error',
                'sync_message': error_msg
            })
            self._log_aws_operation('update_contact_privacy', 'error', error_msg)
            raise UserError(error_msg)
    
    def update_name_servers(self, name_servers):
        """
        Update the name servers for the domain.
        
        Args:
            name_servers: List of name server objects, each with 'Name' and optional 'GlueIps'
        """
        self.ensure_one()
        
        if not self.domain_name:
            return
        
        try:
            # Initialize boto3 client for Route 53 Domains
            r53domains_client = self._get_boto3_client('route53domains')
            
            # Update name servers
            r53domains_client.update_domain_nameservers(
                DomainName=self.domain_name,
                Nameservers=name_servers
            )
            
            # Update the record
            self.write({
                'name_servers': json.dumps(name_servers),
                'sync_status': 'synced',
                'last_sync': fields.Datetime.now(),
                'sync_message': 'Successfully updated name servers'
            })
            
            # Log the action
            self._log_aws_operation('update_name_servers', 'success', 
                                   f"Successfully updated name servers for {self.domain_name}")
            
        except Exception as e:
            error_msg = f"Failed to update name servers: {str(e)}"
            self.write({
                'sync_status': 'error',
                'sync_message': error_msg
            })
            self._log_aws_operation('update_name_servers', 'error', error_msg)
            raise UserError(error_msg)
    
    def create_hosted_zone(self):
        """
        Create a Route 53 hosted zone for this domain if one doesn't already exist.
        """
        self.ensure_one()
        
        if self.hosted_zone_id:
            return self.hosted_zone_id
        
        try:
            # Look for an existing hosted zone
            hosted_zone = self.env['aws.route53.hosted.zone'].search([
                ('domain_name', '=', self.domain_name)
            ], limit=1)
            
            if hosted_zone:
                self.hosted_zone_id = hosted_zone.id
                return hosted_zone
            
            # Create a new hosted zone
            hosted_zone_vals = {
                'domain_name': self.domain_name,
                'comment': f'Hosted zone for registered domain {self.domain_name}',
                'aws_credentials_id': self.aws_credentials_id.id,
                'aws_region': self.aws_region,
            }
            
            hosted_zone = self.env['aws.route53.hosted.zone'].create(hosted_zone_vals)
            
            # Link the hosted zone to this domain
            self.hosted_zone_id = hosted_zone.id
            
            # Log the action
            self._log_aws_operation('create_hosted_zone', 'success', 
                                   f"Successfully created hosted zone for {self.domain_name}")
            
            return hosted_zone
            
        except Exception as e:
            error_msg = f"Failed to create hosted zone: {str(e)}"
            self._log_aws_operation('create_hosted_zone', 'error', error_msg)
            raise UserError(error_msg)
    
    def register_domain(self, domain_name, admin_contact, registrant_contact, tech_contact, 
                       duration_years=1, auto_renew=True, privacy_protection=True):
        """
        Register a new domain with AWS Route 53 Domains.
        
        Args:
            domain_name: The domain name to register
            admin_contact: Dict with admin contact information
            registrant_contact: Dict with registrant contact information
            tech_contact: Dict with technical contact information
            duration_years: Registration duration in years (1-10)
            auto_renew: Whether to enable auto-renewal
            privacy_protection: Whether to enable privacy protection
        
        Returns:
            New domain record
        """
        try:
            # Initialize boto3 client for Route 53 Domains
            r53domains_client = self._get_boto3_client('route53domains')
            
            # Check domain availability
            availability_response = r53domains_client.check_domain_availability(
                DomainName=domain_name
            )
            
            if availability_response.get('Availability') != 'AVAILABLE':
                raise UserError(f"The domain {domain_name} is not available for registration.")
            
            # Get domain pricing
            pricing_response = r53domains_client.get_domain_detail(
                DomainName=domain_name
            )
            
            # Register the domain
            register_response = r53domains_client.register_domain(
                DomainName=domain_name,
                DurationInYears=duration_years,
                AutoRenew=auto_renew,
                AdminContact=admin_contact,
                RegistrantContact=registrant_contact,
                TechContact=tech_contact,
                PrivacyProtectAdminContact=privacy_protection,
                PrivacyProtectRegistrantContact=privacy_protection,
                PrivacyProtectTechContact=privacy_protection
            )
            
            # Create a new domain record
            domain_vals = {
                'domain_name': domain_name,
                'status': 'pending',
                'auto_renew': auto_renew,
                'admin_contact': json.dumps(admin_contact),
                'registrant_contact': json.dumps(registrant_contact),
                'tech_contact': json.dumps(tech_contact),
                'admin_privacy': privacy_protection,
                'registrant_privacy': privacy_protection,
                'tech_privacy': privacy_protection,
                'sync_status': 'synced',
                'last_sync': fields.Datetime.now(),
                'sync_message': 'Domain registration initiated',
                'aws_credentials_id': self._get_aws_credentials_id(),
                'aws_region': self._get_aws_region(),
            }
            
            new_domain = self.create(domain_vals)
            
            # Log the action
            self._log_aws_operation('register_domain', 'success', 
                                   f"Successfully initiated registration for {domain_name}")
            
            return new_domain
            
        except Exception as e:
            error_msg = f"Failed to register domain: {str(e)}"
            self._log_aws_operation('register_domain', 'error', error_msg)
            raise UserError(error_msg)
    
    @api.model
    def import_registered_domains_from_aws(self, aws_credentials_id=None, region_name=None):
        """
        Import all registered domains from AWS Route 53 Domains.
        
        Args:
            aws_credentials_id: Optional AWS credentials ID
            region_name: Optional AWS region name
        
        Returns:
            Action to display imported domains
        """
        try:
            # Use provided credentials or default from context
            if not aws_credentials_id:
                aws_credentials_id = self.env.context.get('aws_credentials_id', False)
            
            if not region_name:
                region_name = self.env.context.get('aws_region', False)
            
            # Initialize boto3 client for Route 53 Domains
            r53domains_client = self._get_boto3_client('route53domains', aws_credentials_id, region_name)
            
            # Get list of domains
            domains = []
            paginator = r53domains_client.get_paginator('list_domains')
            for page in paginator.paginate():
                domains.extend(page.get('Domains', []))
            
            imported_count = 0
            updated_count = 0
            
            for domain_info in domains:
                domain_name = domain_info.get('DomainName')
                
                # Skip if no domain name
                if not domain_name:
                    continue
                
                # Check if domain already exists
                existing = self.search([('domain_name', '=', domain_name)], limit=1)
                
                # Extract basic info from list response
                status = 'unknown'
                if 'Status' in domain_info:
                    aws_status = domain_info['Status']
                    if aws_status in ['registered', 'pending', 'pendingTransfer', 'expired',
                                     'redemptionPeriod', 'autoRenewing', 'pendingDelete',
                                     'transferringAway']:
                        status = aws_status.lower()
                        if status == 'pendingtransfer':
                            status = 'pending_transfer'
                        elif status == 'redemptionperiod':
                            status = 'redemption_period'
                        elif status == 'autorenewing':
                            status = 'auto_renewing'
                        elif status == 'pendingdelete':
                            status = 'pending_delete'
                        elif status == 'transferringaway':
                            status = 'transferring_away'
                
                expiration_date = False
                if 'Expiry' in domain_info:
                    expiration_date = domain_info['Expiry']
                
                # Get full domain details
                try:
                    detail_response = r53domains_client.get_domain_detail(
                        DomainName=domain_name
                    )
                    
                    # Extract auto-renewal setting
                    auto_renew = False
                    if 'AutoRenew' in detail_response:
                        auto_renew = detail_response['AutoRenew']
                    
                    # Extract transfer lock setting
                    transfer_lock = False
                    if 'TransferLock' in detail_response:
                        transfer_lock = detail_response['TransferLock']
                    
                    # Extract contact information
                    admin_contact = {}
                    if 'AdminContact' in detail_response:
                        admin_contact = detail_response['AdminContact']
                    
                    registrant_contact = {}
                    if 'RegistrantContact' in detail_response:
                        registrant_contact = detail_response['RegistrantContact']
                    
                    tech_contact = {}
                    if 'TechContact' in detail_response:
                        tech_contact = detail_response['TechContact']
                    
                    # Extract privacy settings
                    admin_privacy = False
                    if 'AdminPrivacy' in detail_response:
                        admin_privacy = detail_response['AdminPrivacy']
                    
                    registrant_privacy = False
                    if 'RegistrantPrivacy' in detail_response:
                        registrant_privacy = detail_response['RegistrantPrivacy']
                    
                    tech_privacy = False
                    if 'TechPrivacy' in detail_response:
                        tech_privacy = detail_response['TechPrivacy']
                    
                    # Extract name servers
                    name_servers = []
                    if 'Nameservers' in detail_response:
                        name_servers = detail_response['Nameservers']
                    
                    # Extract dates
                    updated_date = False
                    if 'UpdatedDate' in detail_response:
                        updated_date = detail_response['UpdatedDate']
                    
                    registration_date = False
                    if 'CreationDate' in detail_response:
                        registration_date = detail_response['CreationDate']
                    
                    # Look for a matching hosted zone
                    hosted_zone = self.env['aws.route53.hosted.zone'].search([
                        ('domain_name', '=', domain_name)
                    ], limit=1)
                    
                    # Create or update the domain record
                    if existing:
                        existing.write({
                            'status': status,
                            'expiration_date': expiration_date,
                            'updated_date': updated_date,
                            'registration_date': registration_date,
                            'auto_renew': auto_renew,
                            'transfer_lock': transfer_lock,
                            'admin_contact': json.dumps(admin_contact) if admin_contact else '',
                            'registrant_contact': json.dumps(registrant_contact) if registrant_contact else '',
                            'tech_contact': json.dumps(tech_contact) if tech_contact else '',
                            'admin_privacy': admin_privacy,
                            'registrant_privacy': registrant_privacy,
                            'tech_privacy': tech_privacy,
                            'name_servers': json.dumps(name_servers) if name_servers else '',
                            'hosted_zone_id': hosted_zone.id if hosted_zone else False,
                            'sync_status': 'synced',
                            'last_sync': fields.Datetime.now(),
                            'sync_message': 'Successfully imported from AWS'
                        })
                        updated_count += 1
                    else:
                        # Create new domain record
                        self.create({
                            'domain_name': domain_name,
                            'status': status,
                            'expiration_date': expiration_date,
                            'updated_date': updated_date,
                            'registration_date': registration_date,
                            'auto_renew': auto_renew,
                            'transfer_lock': transfer_lock,
                            'admin_contact': json.dumps(admin_contact) if admin_contact else '',
                            'registrant_contact': json.dumps(registrant_contact) if registrant_contact else '',
                            'tech_contact': json.dumps(tech_contact) if tech_contact else '',
                            'admin_privacy': admin_privacy,
                            'registrant_privacy': registrant_privacy,
                            'tech_privacy': tech_privacy,
                            'name_servers': json.dumps(name_servers) if name_servers else '',
                            'hosted_zone_id': hosted_zone.id if hosted_zone else False,
                            'aws_credentials_id': aws_credentials_id,
                            'aws_region': region_name or self._get_default_region(),
                            'sync_status': 'synced',
                            'last_sync': fields.Datetime.now(),
                            'sync_message': 'Successfully imported from AWS'
                        })
                        imported_count += 1
                
                except Exception as e:
                    _logger.warning(f"Could not get full details for domain {domain_name}: {str(e)}")
                    
                    # Create or update with minimal information
                    if existing:
                        existing.write({
                            'status': status,
                            'expiration_date': expiration_date,
                            'sync_status': 'error',
                            'sync_message': f"Could not get full details: {str(e)}"
                        })
                        updated_count += 1
                    else:
                        # Create new domain record with minimal info
                        self.create({
                            'domain_name': domain_name,
                            'status': status,
                            'expiration_date': expiration_date,
                            'aws_credentials_id': aws_credentials_id,
                            'aws_region': region_name or self._get_default_region(),
                            'sync_status': 'error',
                            'sync_message': f"Could not get full details: {str(e)}"
                        })
                        imported_count += 1
            
            # Show a success message
            message = f"Successfully imported {imported_count} new domains and updated {updated_count} existing domains."
            
            # Log the import operation
            self._log_aws_operation('import_registered_domains', 'success', message)
            
            # Return action to display domains
            return {
                'name': _('Imported Registered Domains'),
                'type': 'ir.actions.act_window',
                'res_model': 'aws.route53.registered.domain',
                'view_mode': 'tree,form',
                'target': 'current',
                'context': {
                    'default_aws_credentials_id': aws_credentials_id,
                    'default_aws_region': region_name or self._get_default_region(),
                },
                'help': message,
            }
            
        except Exception as e:
            error_msg = f"Failed to import registered domains: {str(e)}"
            self._log_aws_operation('import_registered_domains', 'error', error_msg)
            raise UserError(error_msg)
    
    def refresh_all_domains(self):
        """
        Refresh all active registered domains.
        """
        domains = self.search([('active', '=', True)])
        for domain in domains:
            try:
                domain.refresh_domain_data()
            except Exception as e:
                _logger.error(f"Failed to refresh domain {domain.domain_name}: {str(e)}")
        
        # Return a notification message
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Domain Refresh'),
                'message': _('Refreshed %s domains.') % len(domains),
                'sticky': False,
                'type': 'success',
            }
        }