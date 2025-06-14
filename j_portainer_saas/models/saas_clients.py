#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class SaasClients(models.Model):
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
    _name = 'j_portainer_saas.saas_clients'
    _description = 'SaaS Clients'
    _order = 'sc_partner_id, sc_subscription_id'
    _rec_name = 'sc_display_name'
    
    # ========================================================================
    # FIELDS
    # ========================================================================
    
    sc_display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name',
        store=True,
        help='Computed display name combining partner and subscription information'
    )
    
    sc_template_id = fields.Many2one(
        comodel_name='subscription.template',
        string='Subscription Template',
        required=True,
        help='The subscription template that defines the SaaS service offering, '
             'including pricing, features, and service specifications'
    )
    
    sc_subscription_id = fields.Many2one(
        comodel_name='subscription.subscription',
        string='Active Subscription',
        required=True,
        help='The active subscription record that manages billing, lifecycle, '
             'and service status for this SaaS client'
    )
    
    sc_stack_id = fields.Many2one(
        comodel_name='j_portainer.stack',
        string='Portainer Stack',
        required=False,
        help='The Portainer stack that deploys and manages the containerized '
             'services for this SaaS client. Can be empty if services are not yet deployed.'
    )
    
    sc_partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Customer Partner',
        required=True,
        help='The partner (customer) record associated with this SaaS client. '
             'Contains contact information, billing details, and relationship data.'
    )
    
    # ========================================================================
    # RELATED FIELDS FOR EASY ACCESS
    # ========================================================================
    
    sc_partner_name = fields.Char(
        string='Customer Name',
        related='sc_partner_id.name',
        readonly=True,
        store=True,
        help='Customer name from the related partner record'
    )
    

    
    sc_template_name = fields.Char(
        string='Template Name',
        related='sc_template_id.name',
        readonly=True,
        store=True,
        help='Name of the subscription template'
    )
    
    sc_stack_name = fields.Char(
        string='Stack Name',
        related='sc_stack_id.name',
        readonly=True,
        store=True,
        help='Name of the associated Portainer stack'
    )
    
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
        help='Indicates if this SaaS client record is active. '
             'Inactive records are hidden from most views but preserved for history.'
    )
    
    sc_notes = fields.Text(
        string='Internal Notes',
        help='Internal notes and comments about this SaaS client. '
             'Not visible to the customer.'
    )
    
    sc_created_date = fields.Datetime(
        string='Created Date',
        default=fields.Datetime.now,
        readonly=True,
        help='Date and time when this SaaS client record was created'
    )
    
    sc_last_updated = fields.Datetime(
        string='Last Updated',
        auto_now=True,
        readonly=True,
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
    # COMPUTED FIELDS
    # ========================================================================
    
    @api.depends('sc_partner_id.name', 'sc_subscription_id.name', 'sc_template_id.name')
    def _compute_display_name(self):
        """
        Compute a meaningful display name for the SaaS client record.
        
        The display name combines partner name, template name, and subscription
        information to provide clear identification in lists and references.
        """
        for record in self:
            partner_name = record.sc_partner_id.name or _('Unknown Partner')
            template_name = record.sc_template_id.name or _('Unknown Template')
            
            if record.sc_subscription_id:
                subscription_ref = record.sc_subscription_id.name or f"Sub #{record.sc_subscription_id.id}"
                record.sc_display_name = f"{partner_name} - {template_name} ({subscription_ref})"
            else:
                record.sc_display_name = f"{partner_name} - {template_name}"
    

    
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
    # ACTION METHODS
    # ========================================================================
    
    def action_view_subscription(self):
        """
        Open the associated subscription record in a form view.
        
        Returns:
            dict: Action dictionary to open the subscription form
        """
        self.ensure_one()
        if not self.sc_subscription_id:
            raise UserError(_('No subscription is associated with this SaaS client.'))
        
        return {
            'name': _('Subscription Details'),
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.subscription',
            'res_id': self.sc_subscription_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
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
    
    def action_view_partner(self):
        """
        Open the associated partner record in a form view.
        
        Returns:
            dict: Action dictionary to open the partner form
        """
        self.ensure_one()
        if not self.sc_partner_id:
            raise UserError(_('No partner is associated with this SaaS client.'))
        
        return {
            'name': _('Customer Details'),
            'type': 'ir.actions.act_window',
            'res_model': 'res.partner',
            'res_id': self.sc_partner_id.id,
            'view_mode': 'form',
            'target': 'current',
        }