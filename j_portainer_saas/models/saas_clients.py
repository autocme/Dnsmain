#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging
import re

_logger = logging.getLogger(__name__)


class SaasClient(models.Model):
    """
    SaaS Clients Management Model
    
    This model manages SaaS clients and their relationships with:
    - Subscription templates for service offerings
    - Active subscriptions for billing and lifecycle management
    - Portainer stacks for containerized service deployment
    - Partner records for customer relationship management
    
    The model serves as a central hub connecting subscription management
    with containerized service deployment through Portainer integration.
    """
    _name = 'saas.client'
    _description = 'SaaS Clients'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sc_sequence, sc_partner_id'
    _rec_name = 'sc_complete_name'
    
    # ========================================================================
    # FIELDS
    # ========================================================================
    
    sc_sequence = fields.Char(
        string='Sequence',
        required=True,
        default=lambda self: _('New'),
        tracking=True,
        help='Unique sequence number for this SaaS client'
    )
    
    sc_complete_name = fields.Char(
        string='Display Name',
        compute='_compute_sc_complete_name',
        help='Display name combining sequence and client name'
    )

    sc_template_id = fields.Many2one(
        comodel_name='sale.subscription.template',
        string='Subscription Template',
        required=False,
        tracking=True, 
        compute='_compute_template_id',
        help='The subscription template that defines the SaaS service offering, '
             'including pricing, features, and service specifications based on subscription period'
    )
    
    sc_deployment_environment_id = fields.Many2one(
        comodel_name='j_portainer.environment',
        string='Deployment Environment',
        compute='_compute_deployment_environment',
        store=False,
        tracking=True,
        help='Auto-selected environment for deployment based on package system type'
    )
    
    sc_subscription_id = fields.Many2one(
        comodel_name='sale.subscription',
        string='Subscription',
        required=False,
        tracking=True,
        help='The active subscription record that manages billing, lifecycle, '
             'and service status for this SaaS client'
    )
    
    sc_subscription_recurring_next_date = fields.Date(
        string="Next invoice date",
        related='sc_subscription_id.recurring_next_date',
        required=False,
        tracking=True,
        help='The Next invoice date for the subscription for this SaaS client'
    )
    
    sc_stack_id = fields.Many2one(
        comodel_name='j_portainer.stack',
        string='Portainer Stack',
        required=False,
        related='sc_portainer_template_id.stack_id',
        tracking=True,
        help='The Portainer stack that deploys and manages the containerized '
             'services for this SaaS client. Can be empty if services are not yet deployed.'
    )
    
    sc_partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Client',
        required=True,
        tracking=True,
        help='The partner (customer) record associated with this SaaS client. '
             'Contains contact information, billing details, and relationship data.'
    )
    
    sc_package_id = fields.Many2one(
        comodel_name='saas.package',
        string='Package',
        required=True,
        tracking=True,
        help='The SaaS package that defines resource limits, pricing, and features '
             'for this client subscription.'
    )
    
    sc_subscription_period = fields.Selection([
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly')
    ], string='Subscription Period',
        default='monthly',
        required=True,
        tracking=True,
        help='Billing frequency determining which subscription template to use from the package')
    
    sc_is_free_trial = fields.Boolean(
        string='Is Free Trial',
        default=False,
        tracking=True,
        help='Indicates whether this client is using the free trial period for their package'
    )
    
    sc_package_has_free_trial = fields.Boolean(
        string='Package Has Free Trial',
        related='sc_package_id.pkg_has_free_trial',
        readonly=True,
        help='Indicates whether the selected package offers free trial option'
    )
    
    sc_portainer_template_id = fields.Many2one(
        comodel_name='j_portainer.customtemplate',
        string='Portainer Template',
        required=False,
        tracking=True,
        help='The Portainer custom template used for deploying containerized services '
             'for this SaaS client.'
    )
    
    sc_status = fields.Selection([
        ('draft', 'Draft'),
        ('running', 'Running'),
        ('freezed', 'Freezed'),
        ('removed', 'Removed'),
    ], string='Status', default='draft', required=True, tracking=True,
       help='Current status of the SaaS client lifecycle')
    
    sc_subdomain_id = fields.Many2one(
        comodel_name='dns.subdomain',
        string='Subdomain',
        help='Auto-created subdomain for this SaaS client based on deployment environment and package domain'
    )
    
    sc_full_domain = fields.Char(
        string='Full Domain',
        related='sc_subdomain_id.full_domain',
        readonly=True,
        help='Complete URL for accessing the SaaS client service'
    )
    
    sc_partner_email = fields.Char(
        string='Client Email',
        related='sc_partner_id.email',
        readonly=True,
        help='Email address of the client'
    )
    
    sc_partner_mobile = fields.Char(
        string='Client Mobile',
        related='sc_partner_id.mobile',
        readonly=True,
        help='Mobile number of the client'
    )
    

    
    sc_container_count = fields.Integer(
        string='Container Count',
        compute='_compute_deployment_stats',
        help='Number of containers deployed for this client'
    )
    
    sc_volume_count = fields.Integer(
        string='Volume Count', 
        compute='_compute_deployment_stats',
        help='Number of volumes created for this client'
    )
    
    sc_network_count = fields.Integer(
        string='Network Count',
        compute='_compute_deployment_stats',
        help='Number of networks used by this client'
    )
    
    sc_invoice_count = fields.Integer(
        string='Invoice Count',
        compute='_compute_invoice_count',
        help='Number of invoices related to this client subscription'
    )
    
    # ========================================================================
    # DOCKER COMPOSE TEMPLATE FIELDS
    # ========================================================================
    
    sc_docker_compose_template = fields.Text(
        string='Docker Compose Template',
        readonly=True, related='sc_package_id.pkg_docker_compose_template',
        help='Docker Compose template inherited from package with variables'
    )
    
    sc_template_variable_ids = fields.One2many(
        comodel_name='saas.template.variable',
        inverse_name='sc_client_id',
        string='Template Variables',
        readonly=True, related='sc_package_id.pkg_template_variable_ids',
        help='Variables inherited from package for template rendering'
    )
    
    sc_rendered_template = fields.Text(
        string='Rendered Template',
        compute='_compute_rendered_template',
        help='Final Docker Compose template with variables replaced by actual values'
    )
    
    # ========================================================================
    # RELATED FIELDS FOR EASY ACCESS
    # ========================================================================
 
    sc_stack_status = fields.Selection(
        string='Stack Status',
        related='sc_stack_id.status',
        readonly=True,
        store=True,
        help='Current status of the Portainer stack (Active, Inactive, Unknown)'
    )
    
    # ========================================================================
    # ADDITIONAL TRACKING FIELDS
    # ========================================================================
    
    sc_active = fields.Boolean(
        string='Active',
        default=True,
        tracking=True,
        help='Indicates if this SaaS client record is active. '
             'Inactive records are hidden from most views but preserved for history.'
    )
    
    sc_notes = fields.Text(
        string='Internal Notes',
        tracking=True,
        help='Internal notes and comments about this SaaS client. '
             'Not visible to the customer.'
    )
    
    sc_created_date = fields.Datetime(
        string='Created Date',
        default=fields.Datetime.now,
        readonly=True,
        tracking=True,
        help='Date and time when this SaaS client record was created'
    )
    
    sc_last_updated = fields.Datetime(
        string='Last Updated',
        auto_now=True,
        readonly=True,
        tracking=True,
        help='Date and time when this record was last modified'
    )
    
    # ========================================================================
    # CONSTRAINTS
    # ========================================================================
    
    _sql_constraints = [
        (
            'unique_sc_sequence',
            'UNIQUE(sc_sequence)',
            'Client sequence must be unique.'
        ),
        (
            'unique_partner_subscription',
            'UNIQUE(sc_partner_id, sc_subscription_id)',
            'A partner can only have one SaaS client record per subscription.'
        ),
        (
            'unique_stack_per_client',
            'UNIQUE(sc_stack_id)',
            'Each Portainer stack can only be associated with one SaaS client.'
        ),
    ]
    
    # ========================================================================
    # VALIDATION METHODS
    # ========================================================================
    
    @api.constrains('sc_subscription_id', 'sc_partner_id')
    def _check_subscription_partner_consistency(self):
        """
        Validate that the subscription belongs to the specified partner.
        
        This ensures data consistency by verifying that the subscription
        record is actually associated with the partner specified in this
        SaaS client record.
        
        Raises:
            ValidationError: If subscription partner doesn't match the specified partner
        """
        for record in self:
            if record.sc_subscription_id and record.sc_partner_id:
                if record.sc_subscription_id.partner_id != record.sc_partner_id:
                    raise ValidationError(_(
                        'The subscription "%s" does not belong to partner "%s". '
                        'Please select a subscription that belongs to the specified partner.'
                    ) % (record.sc_subscription_id.name, record.sc_partner_id.name))
    
    @api.constrains('sc_subscription_id', 'sc_template_id')
    def _check_subscription_template_consistency(self):
        """
        Validate that the subscription uses the specified template.

        This ensures that the subscription was created from the template
        specified in this SaaS client record, maintaining service consistency.

        Raises:
            ValidationError: If subscription template doesn't match the specified template
        """
        for record in self:
            if record.sc_subscription_id and record.sc_template_id:
                if record.sc_subscription_id.template_id != record.sc_template_id:
                    raise ValidationError(_(
                        'The subscription "%s" was not created from template "%s". '
                        'Please select a subscription that matches the specified template.'
                    ) % (record.sc_subscription_id.name, record.sc_template_id.name))
    
    # ========================================================================
    # ONCHANGE METHODS
    # ========================================================================

    @api.onchange('sc_subscription_id')
    def _onchange_subscription_id(self):
        """
        Handle subscription change by auto-filling related fields.
        
        When a subscription is selected, this method automatically
        fills the partner and template fields if they're not already set,
        based on the subscription's data.
        """
        if self.sc_subscription_id:
            # Auto-fill partner if not set
            if not self.sc_partner_id:
                self.sc_partner_id = self.sc_subscription_id.partner_id
            
            # Auto-fill template if not set
            if not self.sc_template_id:
                self.sc_template_id = self.sc_subscription_id.template_id
    

    

    # ========================================================================
    # COMPUTED METHODS
    # ========================================================================


    @api.depends('sc_package_id', 'sc_subscription_period', 'sc_package_id.pkg_mon_subs_template_id', 'sc_package_id.pkg_yea_subs_template_id')
    def _compute_template_id(self):
        """Compute subscription template based on subscription period and package."""
        for record in self:
            if record.sc_package_id:
                # Ensure templates exist on the package - create if needed
                if not record.sc_package_id.pkg_mon_subs_template_id or not record.sc_package_id.pkg_yea_subs_template_id:
                    record.sc_package_id._create_subscription_templates()
                
                if record.sc_subscription_period == 'monthly':
                    template = record.sc_package_id.pkg_mon_subs_template_id
                    record.sc_template_id = template
                    _logger.info(f"SaaS Client {record.id}: Selected MONTHLY template {template.id} with rule_type {template.recurring_rule_type if template else 'None'}")
                elif record.sc_subscription_period == 'yearly':
                    template = record.sc_package_id.pkg_yea_subs_template_id
                    record.sc_template_id = template
                    _logger.info(f"SaaS Client {record.id}: Selected YEARLY template {template.id} with rule_type {template.recurring_rule_type if template else 'None'}")
                else:
                    record.sc_template_id = False
            else:
                record.sc_template_id = False

    @api.depends('sc_package_id', 'sc_package_id.pkg_system_type_id', 'sc_package_id.pkg_system_type_id.st_environment_ids')
    def _compute_deployment_environment(self):
        """Auto-select deployment environment from package system type environments."""
        for record in self:
            if record.sc_package_id and record.sc_package_id.pkg_system_type_id:
                # Get environments from the system type
                environments = record.sc_package_id.pkg_system_type_id.st_environment_ids.filtered(
                    lambda env: env.active and env.status == 'up'
                )
                
                if environments:
                    # Filter environments that allow stack creation
                    available_environments = environments.filtered('allow_stack_creation')
                    
                    if available_environments:
                        # Return the environment with the most available capacity
                        record.sc_deployment_environment_id = available_environments.sorted(
                            lambda env: env.allowed_stack_number - env.active_stack_count, reverse=True
                        )[0]
                    else:
                        # No environments with capacity available
                        record.sc_deployment_environment_id = False
                else:
                    # No active environments in system type
                    record.sc_deployment_environment_id = False
            else:
                # No package or system type selected
                record.sc_deployment_environment_id = False
    
    def _create_subdomain(self):
        """Create subdomain for this SaaS client."""
        self.ensure_one()
        if self.sc_deployment_environment_id and self.sc_package_id and self.sc_package_id.pkg_dns_domain_id and not self.sc_subdomain_id:
            # Get next available number
            existing_subdomains = self.env['dns.subdomain'].search([
                ('domain_id', '=', self.sc_package_id.pkg_dns_domain_id.id)
            ])
            
            # Find highest number in existing subdomain names
            max_number = 0
            for subdomain in existing_subdomains:
                try:
                    number = int(subdomain.name)
                    if number > max_number:
                        max_number = number
                except ValueError:
                    continue
            
            next_number = max_number + 1
            
            # Get IP address for subdomain value
            environment_ip = ''
            
            # Try to use public_url first if it exists
            if hasattr(self.sc_deployment_environment_id, 'public_url') and self.sc_deployment_environment_id.public_url:
                environment_ip = self.sc_deployment_environment_id.public_url
            # Fallback to extracting IP from server URL
            elif self.sc_deployment_environment_id.server_id and self.sc_deployment_environment_id.server_id.url:
                server_url = self.sc_deployment_environment_id.server_id.url
                # Extract IP from URL using regex (matches IPv4 pattern)
                ip_match = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', server_url)
                if ip_match:
                    environment_ip = ip_match.group(1)
                else:
                    # If no IP found, use the original URL as fallback
                    environment_ip = self.sc_deployment_environment_id.url or ''
            else:
                # Final fallback to deployment environment URL
                environment_ip = self.sc_deployment_environment_id.url or ''
            
            # Create subdomain
            subdomain_vals = {
                'name': str(next_number),
                'domain_id': self.sc_package_id.pkg_dns_domain_id.id,
                'type': 'a',
                'value': environment_ip,
                'ttl': 300,
                'saas_client_id': self.id,
            }
            
            subdomain = self.env['dns.subdomain'].create(subdomain_vals)
            self.sc_subdomain_id = subdomain.id

    @api.depends('sc_sequence', 'sc_partner_id', 'sc_partner_id.name')
    def _compute_sc_complete_name(self):
        """Compute display name as sequence/client name."""
        for record in self:
            if record.sc_sequence and record.sc_partner_id:
                record.sc_complete_name = f"{record.sc_sequence}/{record.sc_partner_id.name}"
            elif record.sc_sequence:
                record.sc_complete_name = record.sc_sequence
            elif record.sc_partner_id:
                record.sc_complete_name = record.sc_partner_id.name
            else:
                record.sc_complete_name = 'New SaaS Client'

    @api.depends('sc_docker_compose_template', 'sc_template_variable_ids', 'sc_template_variable_ids.tv_field_name')
    def _compute_rendered_template(self):
        """Render template by replacing variables with actual field values."""
        for record in self:
            if not record.sc_docker_compose_template:
                record.sc_rendered_template = ''
                continue
            
            rendered_content = record.sc_docker_compose_template
            
            # Replace each variable with actual field value
            for variable in record.sc_template_variable_ids:
                if variable.tv_variable_name and variable.tv_field_name:
                    # Get field value from client record
                    field_value = record._get_field_value(variable.tv_field_name)
                    variable_placeholder = f'@{variable.tv_variable_name}@'
                    rendered_content = rendered_content.replace(variable_placeholder, str(field_value))
            
            record.sc_rendered_template = rendered_content
    
    @api.depends('sc_stack_id', 'sc_stack_id.container_ids', 'sc_stack_id.container_ids.volume_ids', 'sc_stack_id.container_ids.volume_ids.volume_id', 'sc_stack_id.container_ids.network_ids')
    def _compute_deployment_stats(self):
        """Compute container, volume, and network counts from deployment stack."""
        for record in self:
            if record.sc_stack_id:
                record.sc_container_count = len(record.sc_stack_id.container_ids)
                
                # Calculate unique volumes from all containers
                unique_volumes = set()
                for container in record.sc_stack_id.container_ids:
                    for volume_relation in container.volume_ids:
                        if volume_relation.volume_id:
                            unique_volumes.add(volume_relation.volume_id.id)
                
                record.sc_volume_count = len(unique_volumes)
                
                # Calculate unique networks from all containers
                unique_networks = set()
                for container in record.sc_stack_id.container_ids:
                    for network_relation in container.network_ids:
                        if network_relation.network_id:
                            unique_networks.add(network_relation.network_id.id)
                
                record.sc_network_count = len(unique_networks)
            else:
                record.sc_container_count = 0
                record.sc_volume_count = 0
                record.sc_network_count = 0
    
    @api.depends('sc_subscription_id', 'sc_subscription_id.invoice_ids')
    def _compute_invoice_count(self):
        """Compute the number of invoices related to this client's subscription."""
        for record in self:
            if record.sc_subscription_id:
                record.sc_invoice_count = len(record.sc_subscription_id.invoice_ids)
            else:
                record.sc_invoice_count = 0

    def name_get(self):
        """Return client display name as sequence/client name."""
        result = []
        for record in self:
            if record.sc_sequence and record.sc_partner_id:
                name = f"{record.sc_sequence}/{record.sc_partner_id.name}"
            elif record.sc_sequence:
                name = record.sc_sequence
            elif record.sc_partner_id:
                name = record.sc_partner_id.name
            else:
                name = 'New SaaS Client'
            result.append((record.id, name))
        return result
    
    def _get_field_value(self, field_path):
        """Get field value from record using dot notation path."""
        if not field_path:
            return ''
        
        try:
            # Split field path by dots (e.g., 'sc_partner_id.name')
            field_parts = field_path.split('.')
            current_record = self
            
            for field_part in field_parts:
                if hasattr(current_record, field_part):
                    current_record = getattr(current_record, field_part)
                else:
                    return ''
            
            # Return the final value as string
            return current_record if current_record else ''
            
        except Exception:
            return ''
    
    # ========================================================================
    # ACTION METHODS
    # ========================================================================

    def action_deploy_client(self):
        self.with_delay().action_deploy()

    def action_deploy(self):
        """Deploy the client template to Portainer by creating custom template and stack."""
        self.ensure_one()
        
        # Validate prerequisites
        if not self.sc_rendered_template:
            raise UserError(_('No rendered template available. Please ensure the package has a Docker Compose template with proper variables.'))
        
        if not self.sc_sequence:
            raise UserError(_('Client sequence is required for deployment.'))
            
        # Check if already deployed
        if self.sc_portainer_template_id:
            raise UserError(_('Client is already deployed. Template: %s') % self.sc_portainer_template_id.title)
        
        # Use the auto-computed deployment environment
        environment = self._get_deployment_environment()
        server = environment.server_id
        
        # Create custom template
        template_vals = {
            'title': self.sc_sequence,
            'description': f'Custom template for SaaS client {self.sc_sequence} ({self.sc_partner_id.name if self.sc_partner_id else "Unknown Client"})',
            'fileContent': self.sc_rendered_template,
            'server_id': server.id,
            'environment_id': environment.id,
        }
        
        try:
            custom_template = self.env['j_portainer.customtemplate'].create(template_vals)
            
            # Link template to client immediately to preserve relationship
            self.sc_portainer_template_id = custom_template.id
            
            # Commit the template creation to ensure it's saved
            self.env.cr.commit()
            
            # Create stack using the template's action
            try:
                stack = custom_template.action_create_stack()
                _logger.info(f'Stack created successfully: {stack.name} (ID: {stack.id})')
                
                # Link stack to client if creation was successful
                if stack and stack.id:
                    # Update the client with the stack reference
                    self.write({
                        'sc_stack_id': stack.id,
                        'sc_status': 'running'
                    })
                    
                    # Ensure the stack has the correct template reference
                    if not stack.custom_template_id:
                        stack.write({'custom_template_id': custom_template.id})
                    
                    self.env.cr.commit()
                    
                    # Log successful deployment
                    self.message_post(
                        body=_('SaaS client successfully deployed to Portainer.<br/>'
                              'Custom Template: %s<br/>'
                              'Stack: %s<br/>'
                              'Server: %s<br/>'
                              'Environment: %s') % (
                            custom_template.title,
                            stack.name,
                            server.name,
                            environment.name
                        ),
                        message_type='notification'
                    )
                    
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Deployment Successful'),
                            'message': _('SaaS client %s has been deployed to Portainer successfully. Stack: %s, just sync the deployment stack resources to get the full details') % (self.sc_sequence, stack.name),
                            'type': 'success',
                            'sticky': True,
                        }
                    }
                else:
                    # Template created but stack creation failed
                    raise UserError(_('Custom template was created successfully, but stack creation failed. Stack record was not returned. Please check the template and try again manually.'))
                    
            except Exception as stack_error:
                # Template was created and linked, but stack creation failed
                # Keep the template relationship intact for manual retry
                raise UserError(_(
                    'Custom template was created successfully, but stack creation failed: %s\n\n'
                    'The template is available in your client record. You can try creating the stack manually from the template.'
                ) % str(stack_error))
                
        except Exception as template_error:
            # Template creation failed entirely
            raise UserError(_('Failed to create custom template: %s') % str(template_error))

    def _get_deployment_environment(self):
        """Get the environment to use for deployment."""
        # Use the computed deployment environment
        if self.sc_deployment_environment_id:
            # Validate the environment is still available
            if not self.sc_deployment_environment_id.active or self.sc_deployment_environment_id.status != 'up':
                raise UserError(_('Auto-selected environment %s is not active or available. Please check environment configuration.') % self.sc_deployment_environment_id.name)
            
            if not self.sc_deployment_environment_id.allow_stack_creation:
                raise UserError(_(
                    'Auto-selected environment %s has reached its stack capacity (%s/%s stacks).\n\n'
                    'Please increase the stack limit or remove unused stacks.'
                ) % (self.sc_deployment_environment_id.name, self.sc_deployment_environment_id.active_stack_count, self.sc_deployment_environment_id.allowed_stack_number))
            
            return self.sc_deployment_environment_id
        
        # No environment available
        if self.sc_package_id and self.sc_package_id.pkg_system_type_id:
            environments = self.sc_package_id.pkg_system_type_id.st_environment_ids.filtered(
                lambda env: env.active and env.status == 'up'
            )
            
            if environments:
                env_details = []
                for env in environments:
                    env_details.append(f"- {env.server_id.name}/{env.name}: {env.active_stack_count}/{env.allowed_stack_number} stacks")
                
                raise UserError(_(
                    'No environments with available stack capacity found for this package system type.\n\n'
                    'Environment stack usage:\n%s\n\n'
                    'Please increase the allowed stack number for an environment or remove unused stacks.'
                ) % '\n'.join(env_details))
            else:
                raise UserError(_('No active environments available for the selected package system type. Please configure environments in the system type.'))
        else:
            raise UserError(_('No package selected or package has no system type configured.'))
    
    # ========================================================================
    # SMART BUTTON ACTIONS
    # ========================================================================
    
    def action_view_custom_template(self):
        """Open the custom template form view."""
        self.ensure_one()
        if not self.sc_portainer_template_id:
            raise UserError(_('No custom template linked to this client.'))
            
        return {
            'type': 'ir.actions.act_window',
            'name': _('Custom Template'),
            'res_model': 'j_portainer.customtemplate',
            'res_id': self.sc_portainer_template_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_view_deployment_stack(self):
        """Open the deployment stack form view."""
        self.ensure_one()
        if not self.sc_stack_id:
            raise UserError(_('No deployment stack linked to this client.'))
            
        return {
            'type': 'ir.actions.act_window',
            'name': _('Deployment Stack'),
            'res_model': 'j_portainer.stack',
            'res_id': self.sc_stack_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_view_containers(self):
        """Open containers list view for this deployment."""
        self.ensure_one()
        if not self.sc_stack_id:
            raise UserError(_('No deployment stack available to show containers.'))
            
        return {
            'type': 'ir.actions.act_window',
            'name': _('Deployment Containers'),
            'res_model': 'j_portainer.container',
            'view_mode': 'tree,form',
            'domain': [('stack_id', '=', self.sc_stack_id.id)],
            'context': {'default_stack_id': self.sc_stack_id.id},
            'target': 'current',
        }
    
    def action_view_volumes(self):
        """Open volumes list view for this deployment."""
        self.ensure_one()
        if not self.sc_stack_id:
            raise UserError(_('No deployment stack available to show volumes.'))
        
        # Get unique volume IDs from all containers in the stack
        volume_ids = set()
        for container in self.sc_stack_id.container_ids:
            for volume_relation in container.volume_ids:
                if volume_relation.volume_id:
                    volume_ids.add(volume_relation.volume_id.id)
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Deployment Volumes'),
            'res_model': 'j_portainer.volume',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', list(volume_ids))],
            'context': {
                'default_server_id': self.sc_stack_id.server_id.id,
                'default_environment_id': self.sc_stack_id.environment_id.id,
            },
            'target': 'current',
        }
    
    def action_view_networks(self):
        """Open networks list view for this deployment."""
        self.ensure_one()
        if not self.sc_stack_id:
            raise UserError(_('No deployment stack available to show networks.'))
        
        # Get unique network IDs from all containers in the stack
        network_ids = set()
        for container in self.sc_stack_id.container_ids:
            for network_relation in container.network_ids:
                if network_relation.network_id:
                    network_ids.add(network_relation.network_id.id)
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Deployment Networks'),
            'res_model': 'j_portainer.network',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', list(network_ids))],
            'context': {
                'default_server_id': self.sc_stack_id.server_id.id,
                'default_environment_id': self.sc_stack_id.environment_id.id,
            },
            'target': 'current',
        }
    
    def action_view_invoices(self):
        """Open invoices list view for this client's subscription."""
        self.ensure_one()
        if not self.sc_subscription_id:
            raise UserError(_('No subscription linked to this client.'))
            
        return {
            'type': 'ir.actions.act_window',
            'name': _('Client Invoices'),
            'res_model': 'account.move',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.sc_subscription_id.invoice_ids.ids)],
            'context': {
                'default_partner_id': self.sc_partner_id.id,
                'default_subscription_id': self.sc_subscription_id.id,
            },
            'target': 'current',
        }
    
    def check_and_deploy_if_invoice_paid(self):
        """Check if subscription invoice is paid and deploy client if needed."""
        self.ensure_one()
        if not self.sc_subscription_id:
            return False
            
        # Check if there are any paid invoices for this subscription
        paid_invoices = self.sc_subscription_id.invoice_ids.filtered(lambda inv: inv.payment_state == 'paid')
        
        if paid_invoices and self.sc_status == 'draft':
            try:
                # Deploy the client
                self.action_deploy_client()
                _logger.info(f"Auto-deployed client {self.id} after invoice payment")
                return True
            except Exception as e:
                _logger.warning(f"Failed to auto-deploy client {self.id} after invoice payment: {e}")
                return False
        
        return False
    
    # ========================================================================
    # BUSINESS METHODS
    # ========================================================================
    
    @api.model
    def create(self, vals):
        """Override create to automatically create subscription for new SaaS clients."""
        if vals.get('sc_sequence', 'New') == 'New':
            vals['sc_sequence'] = self.env['ir.sequence'].next_by_code('saas.client')
        
        # Check if subscription is provided to use as base
        base_subscription_id = vals.get('sc_subscription_id')
        
        # Extract required fields for subscription creation
        partner_id = vals.get('sc_partner_id')
        package_id = vals.get('sc_package_id')
        
        if not base_subscription_id and partner_id and package_id:
            # Get the package and determine correct template based on subscription period
            package = self.env['saas.package'].browse(package_id)
            subscription_period = vals.get('sc_subscription_period', 'monthly')
            
            # Select the appropriate template based on subscription period
            template = None
            if subscription_period == 'monthly' and package.pkg_mon_subs_template_id:
                template = package.pkg_mon_subs_template_id
            elif subscription_period == 'yearly' and package.pkg_yea_subs_template_id:
                template = package.pkg_yea_subs_template_id
            
            if package.exists() and template:
                partner = self.env['res.partner'].browse(partner_id)
                
                # Get free trial setting
                is_free_trial = vals.get('sc_is_free_trial', False)
                _logger.info(f"SaaS Client Creation: is_free_trial={is_free_trial}, package has free trial={package.pkg_has_free_trial}")
                
                # Calculate start date based on free trial
                from datetime import date, timedelta
                start_date = date.today()
                if is_free_trial and package.pkg_has_free_trial:
                    # Get free trial interval from settings
                    config = self.env['ir.config_parameter'].sudo()
                    free_trial_days = int(config.get_param('j_portainer_saas.free_trial_interval_days', 30))
                    start_date = date.today() + timedelta(days=free_trial_days)
                
                # Create subscription values (start with today's date initially)
                subscription_vals = {
                    'partner_id': partner_id,
                    'template_id': template.id,
                    'name': f"{partner.name} - {package.pkg_name} ({subscription_period.title()})",
                    'description': f'SaaS subscription for {partner.name} using {package.pkg_name} package ({subscription_period} billing)',
                    'pricelist_id': partner.property_product_pricelist.id,
                }
                
                # Create the subscription
                subscription = self.env['sale.subscription'].create(subscription_vals)
                
                # Add subscription lines from template products
                for product_template in template.product_ids:
                    if product_template.is_saas_product:
                        # Get the product variant (product.product) from template
                        product_variant = product_template.product_variant_id
                        if product_variant:
                            line_vals = {
                                'sale_subscription_id': subscription.id,
                                'product_id': product_variant.id,
                                'name': product_template.name,
                                'price_unit': product_template.list_price,
                                'product_uom_qty': 1,
                            }
                            self.env['sale.subscription.line'].create(line_vals)
                
                # Start the subscription first (sets proper stage and status)
                subscription.action_start_subscription()
                
                # Now apply the custom start date after subscription is started
                if start_date != date.today():
                    subscription.write({'date_start': start_date})
                    _logger.info(f"Updated subscription {subscription.name} start date to {start_date} for free trial")
                
                # Set the subscription ID in vals
                vals['sc_subscription_id'] = subscription.id
                
                # Generate first invoice for paid subscriptions (not free trial)
                if not is_free_trial:
                    try:
                        # Create first invoice using manual_invoice method
                        subscription.manual_invoice()
                        _logger.info(f"First invoice generated for paid subscription {subscription.name}")
                    except Exception as e:
                        _logger.warning(f"Failed to generate first invoice for subscription {subscription.name}: {e}")
                
                _logger.info(f"Auto-created {subscription_period} subscription {subscription.name} for SaaS client (Free Trial: {is_free_trial})")
        
        # Create the SaaS client
        client = super().create(vals)
        
        # Create subdomain after record creation
        client._create_subdomain()
        
        return client

    # ========================================================================
    # ACTION METHODS
    # ========================================================================
    

