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
    _rec_name = 'sc_display_name'
    
    # ========================================================================
    # FIELDS
    # ========================================================================
    
    sc_sequence = fields.Char(
        string='Sequence',
        required=True,
        default=lambda self: self._get_default_sequence(),
        tracking=True,
        help='Unique sequence number for this SaaS client'
    )
    
    sc_display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name',
        store=True,
        help='Display name combining sequence and client name'
    )
    
    sc_template_id = fields.Many2one(
        comodel_name='sale.subscription.template',
        string='Subscription Template',
        required=False,
        tracking=True, related='sc_package_id.pkg_subscription_template_id',
        help='The subscription template that defines the SaaS service offering, '
             'including pricing, features, and service specifications'
    )
    
    sc_subscription_id = fields.Many2one(
        comodel_name='sale.subscription',
        string='Subscription',
        required=False,
        tracking=True,
        help='The active subscription record that manages billing, lifecycle, '
             'and service status for this SaaS client'
    )
    
    sc_stack_id = fields.Many2one(
        comodel_name='j_portainer.stack',
        string='Portainer Stack',
        required=False,
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
    
    sc_portainer_template_id = fields.Many2one(
        comodel_name='j_portainer.customtemplate',
        string='Portainer Template',
        required=False,
        tracking=True,
        help='The Portainer custom template used for deploying containerized services '
             'for this SaaS client.'
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
    
    def _get_default_sequence(self):
        """Generate default sequence for new client records."""
        sequence = self.env['ir.sequence'].next_by_code('saas.client.sequence')
        if not sequence:
            # Fallback if sequence doesn't exist
            last_client = self.env['saas.client'].search([], order='sc_sequence desc', limit=1)
            if last_client and last_client.sc_sequence:
                try:
                    last_number = int(last_client.sc_sequence[2:])  # Remove 'SC' prefix
                    return f'SC{last_number + 1:05d}'
                except (ValueError, IndexError):
                    pass
            return 'SC00001'
        return sequence
    
    @api.depends('sc_sequence', 'sc_partner_id', 'sc_partner_id.name')
    def _compute_display_name(self):
        """Compute display name as sequence/client name."""
        for record in self:
            if record.sc_sequence and record.sc_partner_id:
                record.sc_display_name = f"{record.sc_sequence}/{record.sc_partner_id.name}"
            elif record.sc_sequence:
                record.sc_display_name = record.sc_sequence
            elif record.sc_partner_id:
                record.sc_display_name = record.sc_partner_id.name
            else:
                record.sc_display_name = 'New SaaS Client'
    
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
    # BUSINESS METHODS
    # ========================================================================
    
    @api.model
    def create(self, vals):
        """Override create to automatically create subscription for new SaaS clients."""
        # Check if subscription is provided to use as base
        base_subscription_id = vals.get('sc_subscription_id')
        
        # Extract required fields for subscription creation
        partner_id = vals.get('sc_partner_id')
        package_id = vals.get('sc_package_id')
        
        if not base_subscription_id and partner_id and package_id:
            # Get the package and its template
            package = self.env['saas.package'].browse(package_id)
            if package.exists() and package.pkg_subscription_template_id:
                template = package.pkg_subscription_template_id
                partner = self.env['res.partner'].browse(partner_id)
                
                # Create subscription values
                subscription_vals = {
                    'partner_id': partner_id,
                    'template_id': template.id,
                    'name': f"{partner.name} - {package.pkg_name}",
                    'description': f'SaaS subscription for {partner.name} using {package.pkg_name} package',
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
                # Set the subscription ID in vals
                vals['sc_subscription_id'] = subscription.id
                
                _logger.info(f"Auto-created subscription {subscription.name} for SaaS client")
        
        # Create the SaaS client
        client = super().create(vals)
        
        return client

    # ========================================================================
    # ACTION METHODS
    # ========================================================================
    

