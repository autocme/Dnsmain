#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

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
    _order = 'sc_partner_id, sc_subscription_id'
    _rec_name = 'sc_partner_id'
    
    # ========================================================================
    # FIELDS
    # ========================================================================
    

    
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
        required=True,
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
    
    @api.onchange('sc_template_id')
    def _onchange_template_id(self):
        """
        Handle template change by filtering available subscriptions.
        
        When a template is selected, this method updates the domain
        for the subscription field to only show subscriptions that
        were created from the selected template.
        """
        if self.sc_template_id:
            return {
                'domain': {
                    'sc_subscription_id': [
                        ('template_id', '=', self.sc_template_id.id)
                    ]
                }
            }
        else:
            return {
                'domain': {
                    'sc_subscription_id': []
                }
            }
    
    @api.onchange('sc_partner_id')
    def _onchange_partner_id(self):
        """
        Handle partner change by filtering available subscriptions.
        
        When a partner is selected, this method updates the domain
        for the subscription field to only show subscriptions that
        belong to the selected partner.
        """
        if self.sc_partner_id:
            domain = [('partner_id', '=', self.sc_partner_id.id)]
            
            # If template is also selected, add template filter
            if self.sc_template_id:
                template_filter = ('template_id', '=', self.sc_template_id.id)
                domain = domain + [template_filter]
            
            return {
                'domain': {
                    'sc_subscription_id': domain
                }
            }
        else:
            return {
                'domain': {
                    'sc_subscription_id': []
                }
            }
    
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
                    'state': 'draft',
                }
                
                # Create the subscription
                subscription = self.env['sale.subscription'].create(subscription_vals)
                
                # Add subscription lines from template products
                for product in template.product_ids:
                    if product.is_saas_product:
                        line_vals = {
                            'subscription_id': subscription.id,
                            'product_id': product.id,
                            'name': product.name,
                            'price_unit': product.list_price,
                            'quantity': 1,
                        }
                        self.env['sale.subscription.line'].create(line_vals)
                
                # Set the subscription ID in vals
                vals['sc_subscription_id'] = subscription.id
                
                _logger.info(f"Auto-created subscription {subscription.name} for SaaS client")
        
        # Create the SaaS client
        client = super().create(vals)
        
        return client
    
    def create_subscription(self):
        """
        Create a subscription for this SaaS client using the package template.
        This method can be called manually if subscription wasn't auto-created.
        """
        self.ensure_one()
        
        if self.sc_subscription_id:
            _logger.warning(f"SaaS client {self.sc_partner_id.name} already has a subscription")
            return self.sc_subscription_id
        
        if not self.sc_package_id or not self.sc_package_id.pkg_subscription_template_id:
            raise UserError(_('Cannot create subscription: Package or template is missing.'))
        
        template = self.sc_package_id.pkg_subscription_template_id
        
        # Create subscription values
        subscription_vals = {
            'partner_id': self.sc_partner_id.id,
            'template_id': template.id,
            'name': f"{self.sc_partner_id.name} - {self.sc_package_id.pkg_name}",
            'description': f'SaaS subscription for {self.sc_partner_id.name} using {self.sc_package_id.pkg_name} package',
            'pricelist_id': self.sc_partner_id.property_product_pricelist.id,
            'state': 'draft',
        }
        
        # Create the subscription
        subscription = self.env['sale.subscription'].create(subscription_vals)
        
        # Add subscription lines from template products
        for product in template.product_ids:
            if product.is_saas_product:
                line_vals = {
                    'subscription_id': subscription.id,
                    'product_id': product.id,
                    'name': product.name,
                    'price_unit': product.list_price,
                    'quantity': 1,
                }
                self.env['sale.subscription.line'].create(line_vals)
        
        # Update client with subscription
        self.write({'sc_subscription_id': subscription.id})
        
        _logger.info(f"Created subscription {subscription.name} for SaaS client {self.sc_partner_id.name}")
        return subscription
    
    # ========================================================================
    # ACTION METHODS
    # ========================================================================
    
    
    def action_view_stack(self):
        """
        Open the associated Portainer stack record in a form view.
        
        Returns:
            dict: Action dictionary to open the stack form
        """
        self.ensure_one()
        if not self.sc_stack_id:
            raise UserError(_('No Portainer stack is associated with this SaaS client.'))
        
        return {
            'name': _('Portainer Stack Details'),
            'type': 'ir.actions.act_window',
            'res_model': 'j_portainer.stack',
            'res_id': self.sc_stack_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
    