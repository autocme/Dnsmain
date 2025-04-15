# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
#
# Copyright (C) 2023 JAAH

import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

class Route53HostedZone(models.Model):
    """
    Represents an AWS Route 53 hosted zone.
    """
    _name = 'aws.route53.hosted.zone'
    _description = 'Route 53 Hosted Zone'
    _inherit = ['aws.service.implementation.mixin', 'aws.service.logger']
    _rec_name = 'domain_name'
    _order = 'domain_name'
    
    domain_name = fields.Char(string='Domain Name', required=True, index=True)
    hosted_zone_id = fields.Char(string='Hosted Zone ID', index=True, readonly=True)
    caller_reference = fields.Char(string='Caller Reference', readonly=True)
    description = fields.Text(string='Description')
    comment = fields.Text(string='Comment')
    
    is_private = fields.Boolean(string='Private Zone', default=False)
    vpc_id = fields.Char(string='VPC ID', help='For private hosted zones')
    vpc_region = fields.Char(string='VPC Region', help='For private hosted zones')
    
    record_count = fields.Integer(string='Record Count', compute='_compute_record_count')
    name_servers = fields.Char(string='Name Servers', readonly=True)
    
    active = fields.Boolean(default=True)
    sync_status = fields.Selection([
        ('not_synced', 'Not Synced'),
        ('syncing', 'Syncing'),
        ('synced', 'Synced'),
        ('error', 'Error')
    ], string='Sync Status', default='not_synced')
    last_sync = fields.Datetime(string='Last Sync')
    sync_message = fields.Text(string='Sync Message')
    
    record_ids = fields.One2many('aws.route53.dns.record', 'hosted_zone_id', string='DNS Records')
    
    _sql_constraints = [
        ('domain_name_unique', 'UNIQUE(domain_name)', 'Domain name must be unique!')
    ]
    
    @api.depends('record_ids')
    def _compute_record_count(self):
        """Compute the number of DNS records in this hosted zone"""
        for zone in self:
            zone.record_count = len(zone.record_ids)
    
    @api.model
    def create(self, vals):
        """
        Create a new Route 53 hosted zone both in Odoo and AWS.
        """
        # Create locally first
        zone = super(Route53HostedZone, self).create(vals)
        
        # Don't create in AWS if sync is disabled or for data import
        if self.env.context.get('import_file') or self.env.context.get('no_aws_sync'):
            return zone
        
        # Create in AWS
        try:
            zone._create_hosted_zone_in_aws()
        except Exception as e:
            zone.write({
                'sync_status': 'error',
                'sync_message': str(e)
            })
            _logger.error("Failed to create Route 53 hosted zone: %s", str(e))
            
        return zone
    
    def unlink(self):
        """
        Delete the hosted zone from AWS before deleting from Odoo.
        """
        for zone in self:
            if zone.hosted_zone_id and not self.env.context.get('no_aws_sync'):
                try:
                    zone._delete_hosted_zone_from_aws()
                except Exception as e:
                    raise UserError(_("Cannot delete hosted zone %s from AWS: %s") % (zone.domain_name, str(e)))
        
        return super(Route53HostedZone, self).unlink()
    
    def _create_hosted_zone_in_aws(self):
        """
        Create the hosted zone in AWS Route 53.
        """
        self.ensure_one()
        
        # Get Route 53 client
        route53 = self.get_service_client('route53')
        
        # Prepare parameters
        params = {
            'Name': self.domain_name,
            'CallerReference': self.caller_reference or self.domain_name + str(fields.Datetime.now()),
        }
        
        if self.comment:
            params['HostedZoneConfig'] = {
                'Comment': self.comment,
                'PrivateZone': self.is_private
            }
            
        # For private hosted zones, add VPC information
        if self.is_private:
            if not self.vpc_id or not self.vpc_region:
                raise ValidationError(_("VPC ID and VPC Region are required for private hosted zones."))
                
            params['VPC'] = {
                'VPCId': self.vpc_id,
                'VPCRegion': self.vpc_region
            }
        
        # Create the hosted zone
        success, result = self.aws_operation_with_logging(
            service_name='route53',
            operation='create_hosted_zone',
            with_result=True,
            **params
        )
        
        if not success:
            raise UserError(_("Failed to create hosted zone: %s") % result)
            
        # Update local record with AWS data
        hosted_zone = result.get('HostedZone', {})
        name_servers = result.get('DelegationSet', {}).get('NameServers', [])
        
        self.write({
            'hosted_zone_id': hosted_zone.get('Id', '').replace('/hostedzone/', ''),
            'caller_reference': hosted_zone.get('CallerReference'),
            'name_servers': ', '.join(name_servers),
            'sync_status': 'synced',
            'last_sync': fields.Datetime.now(),
            'sync_message': _("Hosted zone created successfully")
        })
    
    def _delete_hosted_zone_from_aws(self):
        """
        Delete the hosted zone from AWS Route 53.
        """
        self.ensure_one()
        
        if not self.hosted_zone_id:
            return
            
        # Get Route 53 client
        route53 = self.get_service_client('route53')
        
        # Delete the hosted zone
        success, result = self.aws_operation_with_logging(
            service_name='route53',
            operation='delete_hosted_zone',
            with_result=True,
            Id=self.hosted_zone_id
        )
        
        if not success:
            raise UserError(_("Failed to delete hosted zone: %s") % result)
    
    def import_records_from_aws(self):
        """
        Import DNS records from AWS Route 53 for this hosted zone.
        """
        self.ensure_one()
        
        if not self.hosted_zone_id:
            raise UserError(_("No hosted zone ID. Cannot import records."))
            
        # Get Route 53 client
        route53 = self.get_service_client('route53')
        
        # Update status
        self.write({
            'sync_status': 'syncing',
            'sync_message': _("Importing records...")
        })
        
        try:
            # Get all records from AWS
            success, result = self.aws_operation_with_logging(
                service_name='route53',
                operation='list_resource_record_sets',
                with_result=True,
                HostedZoneId=self.hosted_zone_id
            )
            
            if not success:
                raise UserError(_("Failed to list DNS records: %s") % result)
                
            record_sets = result.get('ResourceRecordSets', [])
            
            # Process record sets
            Route53DNSRecord = self.env['aws.route53.dns.record']
            
            # Create context to avoid creating records in AWS again
            ctx = dict(self.env.context, no_aws_sync=True)
            
            # Process records
            for record_set in record_sets:
                record_name = record_set.get('Name', '')
                record_type = record_set.get('Type', '')
                ttl = record_set.get('TTL', 300)
                
                # Skip SOA and NS records for the zone itself
                if record_type in ['SOA', 'NS'] and (record_name == self.domain_name or record_name == self.domain_name + '.'):
                    continue
                
                # Check if record already exists
                domain = self.domain_name
                if domain.endswith('.'):
                    domain = domain[:-1]
                    
                if record_name.endswith('.'):
                    record_name = record_name[:-1]
                    
                # Extract subdomain from full name
                subdomain = ''
                if record_name != domain:
                    if record_name.endswith(domain):
                        subdomain = record_name[:-len(domain)-1]  # -1 for the dot
                
                # Find existing record
                existing = Route53DNSRecord.search([
                    ('hosted_zone_id', '=', self.id),
                    ('name', '=', subdomain or '@'),
                    ('type', '=', record_type)
                ])
                
                # Prepare values
                resource_records = record_set.get('ResourceRecords', [])
                values = [r.get('Value', '') for r in resource_records]
                values_str = ';'.join(values)
                
                if existing:
                    # Update existing record
                    existing.with_context(ctx).write({
                        'ttl': ttl,
                        'value': values_str,
                        'sync_status': 'synced',
                        'last_sync': fields.Datetime.now(),
                    })
                else:
                    # Create new record
                    Route53DNSRecord.with_context(ctx).create({
                        'hosted_zone_id': self.id,
                        'name': subdomain or '@',
                        'type': record_type,
                        'ttl': ttl,
                        'value': values_str,
                        'sync_status': 'synced',
                        'last_sync': fields.Datetime.now(),
                    })
            
            # Update zone status
            self.write({
                'sync_status': 'synced',
                'last_sync': fields.Datetime.now(),
                'sync_message': _("Successfully imported %s records") % len(record_sets)
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _("Successfully imported %s records") % len(record_sets),
                    'sticky': False,
                    'type': 'success',
                }
            }
            
        except Exception as e:
            self.write({
                'sync_status': 'error',
                'sync_message': str(e)
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
    def import_hosted_zones_from_aws(self, aws_credentials_id=None, region_name=None):
        """
        Import all hosted zones from AWS Route 53.
        
        Args:
            aws_credentials_id: Optional AWS credentials ID
            region_name: Optional AWS region name
        """
        # Get Route 53 client
        route53 = self.get_aws_client('route53', aws_credentials_id=aws_credentials_id, region_name=region_name)
        
        try:
            # Get all hosted zones from AWS
            response = route53.list_hosted_zones()
            hosted_zones = response.get('HostedZones', [])
            
            # Create context to avoid creating zones in AWS again
            ctx = dict(self.env.context, no_aws_sync=True)
            
            # Process hosted zones
            for zone in hosted_zones:
                zone_id = zone.get('Id', '').replace('/hostedzone/', '')
                zone_name = zone.get('Name', '')
                
                # Remove trailing dot from domain name
                if zone_name.endswith('.'):
                    zone_name = zone_name[:-1]
                    
                # Check if zone already exists
                existing = self.search([('hosted_zone_id', '=', zone_id)])
                
                if existing:
                    # Update existing zone
                    existing.with_context(ctx).write({
                        'domain_name': zone_name,
                        'caller_reference': zone.get('CallerReference'),
                        'comment': zone.get('Config', {}).get('Comment', ''),
                        'is_private': zone.get('Config', {}).get('PrivateZone', False),
                        'sync_status': 'synced',
                        'last_sync': fields.Datetime.now(),
                    })
                else:
                    # Create new zone
                    new_zone = self.with_context(ctx).create({
                        'domain_name': zone_name,
                        'hosted_zone_id': zone_id,
                        'caller_reference': zone.get('CallerReference'),
                        'comment': zone.get('Config', {}).get('Comment', ''),
                        'is_private': zone.get('Config', {}).get('PrivateZone', False),
                        'sync_status': 'synced',
                        'last_sync': fields.Datetime.now(),
                    })
                    
                    # Get name servers
                    try:
                        ns_response = route53.get_hosted_zone(Id=zone_id)
                        name_servers = ns_response.get('DelegationSet', {}).get('NameServers', [])
                        new_zone.write({
                            'name_servers': ', '.join(name_servers)
                        })
                    except Exception as e:
                        _logger.warning("Failed to get name servers for zone %s: %s", zone_name, str(e))
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _("Successfully imported %s hosted zones") % len(hosted_zones),
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
            
    def check_dns_propagation(self):
        """
        Check DNS propagation for this hosted zone.
        """
        self.ensure_one()
        
        if not self.hosted_zone_id:
            raise UserError("No hosted zone ID available. The zone might not be synchronized with AWS.")
        
        try:
            # Initialize boto3 client
            r53_client = self._get_boto3_client('route53')
            
            # Get nameservers for this hosted zone
            response = r53_client.get_hosted_zone(Id=self.hosted_zone_id)
            nameservers = response.get('DelegationSet', {}).get('NameServers', [])
            
            if not nameservers:
                raise UserError("No nameservers found for this hosted zone.")
            
            # Construct message with nameservers
            nameserver_list = "\n".join([f"- {ns}" for ns in nameservers])
            message = f"""
DNS Propagation Check for {self.domain_name}:

The following nameservers are configured for this domain:
{nameserver_list}

To check DNS propagation:
1. Use an online DNS propagation checker like https://www.whatsmydns.net/ or https://dnschecker.org/
2. Enter your domain name ({self.domain_name})
3. Select the record type you want to check
4. The tool will show the propagation status across different DNS servers worldwide

For more detailed checking:
- Use command line tools like 'dig' or 'nslookup'
- Example: dig @{nameservers[0]} {self.domain_name} ANY
- This will query a specific nameserver for your domain records
            """
            
            # Return the message as a dialog
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('DNS Propagation Information'),
                    'message': message,
                    'sticky': True,
                    'type': 'info',
                }
            }
        
        except Exception as e:
            error_msg = f"Failed to check DNS propagation: {str(e)}"
            self._log_aws_operation('check_dns_propagation', 'error', error_msg)
            raise UserError(error_msg)
    
    def create_dnssec_key(self):
        """
        Create a DNSSEC key for this hosted zone.
        """
        self.ensure_one()
        
        if not self.hosted_zone_id:
            raise UserError("No hosted zone ID available. The zone might not be synchronized with AWS.")
        
        try:
            # Initialize boto3 client
            r53_client = self._get_boto3_client('route53')
            
            # Check if DNSSEC is already enabled
            try:
                dnssec_status = r53_client.get_dnssec(
                    HostedZoneId=self.hosted_zone_id
                )
                if dnssec_status.get('Status', {}).get('ServeSignature') == 'SIGNING':
                    raise UserError("DNSSEC is already enabled for this hosted zone.")
            except r53_client.exceptions.ClientError as e:
                if 'NoSuchHostedZone' not in str(e):
                    # If error is not "no DNSSEC config exists", re-raise
                    raise
            
            # Enable DNSSEC for the hosted zone
            response = r53_client.enable_dnssec_signing(
                HostedZoneId=self.hosted_zone_id
            )
            
            # Extract key info
            key_info = ""
            if 'KeySigningKey' in response:
                key_info = f"""
Key Signing Key information:
- Name: {response['KeySigningKey'].get('Name', 'N/A')}
- Status: {response['KeySigningKey'].get('Status', 'N/A')}
- KSK length: {response['KeySigningKey'].get('KSKLength', 'N/A')}
- DNSKEY record: {response['KeySigningKey'].get('DNSKEYRecord', 'N/A')}
                """
            
            # Log the success
            self._log_aws_operation('create_dnssec_key', 'success', 
                                   f"Successfully enabled DNSSEC for {self.domain_name}")
            
            # Show success message
            message = f"""
DNSSEC has been successfully enabled for {self.domain_name}.

{key_info}

To fully implement DNSSEC:
1. Make sure the domain registrar supports DNSSEC
2. Add the DS (Delegation Signer) record to your domain at the registrar
3. This process can take 24-48 hours to fully propagate
            """
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('DNSSEC Enabled'),
                    'message': message,
                    'sticky': True,
                    'type': 'success',
                }
            }
        
        except Exception as e:
            error_msg = f"Failed to enable DNSSEC: {str(e)}"
            self._log_aws_operation('create_dnssec_key', 'error', error_msg)
            raise UserError(error_msg)
    
    def action_view_records(self):
        """
        Open a view with all DNS records for this hosted zone.
        """
        self.ensure_one()
        return {
            'name': _('DNS Records for %s') % self.domain_name,
            'type': 'ir.actions.act_window',
            'res_model': 'aws.route53.dns.record',
            'view_mode': 'tree,form',
            'domain': [('hosted_zone_id', '=', self.id)],
            'context': {'default_hosted_zone_id': self.id},
        }