#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class SaasPackage(models.Model):
    """
    Package Management Model
    
    This model defines SaaS packages with resource limits and pricing.
    Each package specifies user limits, company limits, database constraints,
    and billing information for SaaS client subscriptions.
    """
    _name = 'saas.package'
    _description = 'SaaS Package'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'pkg_sequence, pkg_name'
    _rec_name = 'pkg_name'
    
    # ========================================================================
    # FIELDS
    # ========================================================================
    
    pkg_sequence = fields.Char(
        string='Package Sequence',
        readonly=True,
        copy=False,
        tracking=True,
        help='Auto-generated sequence code for package ordering (e.g., PK00001)'
    )
    
    pkg_name = fields.Char(
        string='Package Name',
        required=True,
        translate=True,
        tracking=True,
        help='Display name of the SaaS package'
    )
    
    pkg_user_limit = fields.Integer(
        string='User Limit',
        default=2,
        required=True,
        tracking=True,
        help='Maximum number of users allowed in this package'
    )
    
    pkg_company_limit = fields.Integer(
        string='Company Limit',
        default=1,
        required=True,
        tracking=True,
        help='Maximum number of companies allowed in this package'
    )
    
    pkg_warning_delay = fields.Integer(
        string='Warning Delay',
        default=7,
        required=True,
        tracking=True,
        help='Number of days before due date to send warning notifications'
    )
    
    pkg_database_limit_size = fields.Float(
        string='Database Limit Size (GB)',
        default=2.0,
        required=True,
        tracking=True,
        help='Maximum database storage size allowed in gigabytes'
    )
    
    pkg_drop_after_days_frozen = fields.Integer(
        string='Drop After Days Frozen',
        default=30,
        required=True,
        tracking=True,
        help='Number of days after freezing before database is permanently dropped'
    )
    
    pkg_freezing_db_due_balance_days = fields.Integer(
        string='Freezing DB base on due balance (Days)',
        default=30,
        required=True,
        tracking=True,
        help='Number of days after due date before database is frozen'
    )
    
    pkg_price = fields.Monetary(
        string='Price',
        currency_field='currency_id',
        tracking=True,
        help='Monthly subscription price for this package'
    )
    
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
        required=True,
        tracking=True,
        help='Currency for package pricing'
    )
    
    pkg_subscription_template_id = fields.Many2one(
        comodel_name='sale.subscription.template',
        string='Subscription Template',
        required=True,
        tracking=True,
        help='Associated subscription template for billing and lifecycle management'
    )
    
    # ========================================================================
    # ADDITIONAL TRACKING FIELDS
    # ========================================================================
    
    pkg_active = fields.Boolean(
        string='Active',
        default=True,
        tracking=True,
        help='Indicates if this package is available for new subscriptions'
    )
    
    pkg_description = fields.Text(
        string='Description',
        translate=True,
        tracking=True,
        help='Detailed description of package features and limitations'
    )
    
    pkg_created_date = fields.Datetime(
        string='Created Date',
        default=fields.Datetime.now,
        readonly=True,
        tracking=True,
        help='Date and time when this package was created'
    )
    
    pkg_last_updated = fields.Datetime(
        string='Last Updated',
        auto_now=True,
        readonly=True,
        tracking=True,
        help='Date and time when this record was last modified'
    )
    
    # ========================================================================
    # COMPUTED FIELDS
    # ========================================================================
    
    saas_client_count = fields.Integer(
        string='SaaS Clients Count',
        compute='_compute_saas_client_count',
        help='Number of SaaS clients using this package'
    )
    
    # ========================================================================
    # CONSTRAINTS
    # ========================================================================
    
    _sql_constraints = [
        (
            'unique_package_sequence',
            'UNIQUE(pkg_sequence)',
            'Package sequence must be unique.'
        ),
        (
            'unique_package_name',
            'UNIQUE(pkg_name)',
            'Package name must be unique.'
        ),
        (
            'positive_user_limit',
            'CHECK(pkg_user_limit > 0)',
            'User limit must be greater than zero.'
        ),
        (
            'positive_company_limit',
            'CHECK(pkg_company_limit > 0)',
            'Company limit must be greater than zero.'
        ),
        (
            'positive_database_size',
            'CHECK(pkg_database_limit_size > 0)',
            'Database size limit must be greater than zero.'
        ),
        (
            'positive_warning_delay',
            'CHECK(pkg_warning_delay >= 0)',
            'Warning delay must be zero or positive.'
        ),
        (
            'positive_drop_days',
            'CHECK(pkg_drop_after_days_frozen > 0)',
            'Drop after days frozen must be greater than zero.'
        ),
        (
            'positive_freezing_days',
            'CHECK(pkg_freezing_db_due_balance_days > 0)',
            'Freezing days must be greater than zero.'
        ),
    ]
    
    # ========================================================================
    # COMPUTED METHODS
    # ========================================================================
    
    def _compute_saas_client_count(self):
        """Compute the number of SaaS clients using this package."""
        for record in self:
            record.saas_client_count = self.env['saas.client'].search_count([
                ('sc_package_id', '=', record.id)
            ])
    
    # ========================================================================
    # VALIDATION METHODS
    # ========================================================================
    
    @api.constrains('pkg_price')
    def _check_price_positive(self):
        """Validate that package price is not negative."""
        for record in self:
            if record.pkg_price and record.pkg_price < 0:
                raise ValidationError(_('Package price cannot be negative.'))
    
    @api.constrains('pkg_drop_after_days_frozen', 'pkg_freezing_db_due_balance_days')
    def _check_logical_freeze_drop_sequence(self):
        """Validate that drop days are greater than or equal to freezing days."""
        for record in self:
            if record.pkg_drop_after_days_frozen < record.pkg_freezing_db_due_balance_days:
                raise ValidationError(_(
                    'Drop after days frozen (%d) should be greater than or equal to '
                    'freezing days (%d) to ensure logical sequence.'
                ) % (record.pkg_drop_after_days_frozen, record.pkg_freezing_db_due_balance_days))
    
    # ========================================================================
    # BUSINESS METHODS
    # ========================================================================

    def name_get(self):
        """Return package name with pricing information."""
        result = []
        for record in self:
            name = record.pkg_name
            if record.pkg_price and record.currency_id:
                name = f"{name} ({record.currency_id.symbol}{record.pkg_price:.2f})"
            result.append((record.id, name))
        return result
    
    @api.model
    def create(self, vals):
        """Override create to generate sequence number and create subscription template."""
        if not vals.get('pkg_sequence'):
            vals['pkg_sequence'] = self.env['ir.sequence'].next_by_code('saas.package')
        
        # Create the package first
        package = super().create(vals)
        
        # Auto-create subscription template
        template_vals = {
            'name': package.pkg_name,
        }
        
        # Create template with SaaS context
        template = self.env['sale.subscription.template'].with_context(
            from_saas_package=True,
            saas_package_id=package.id,
            saas_package_name=package.pkg_name,
            saas_package_price=package.pkg_price or 0.0
        ).create(template_vals)
        
        # Update package with template reference
        package.write({'pkg_subscription_template_id': template.id})
        
        _logger.info(f"Created subscription template {template.name} for SaaS package {package.pkg_name}")
        
        return package

    def write(self, vals):
        """Override write to sync changes to subscription template and product."""
        result = super().write(vals)
        
        # Only sync if not coming from product or template sync to avoid infinite loops
        if not self.env.context.get('skip_template_sync') and not self.env.context.get('skip_product_sync'):
            # Sync name changes
            if 'pkg_name' in vals and self.pkg_subscription_template_id:
                try:
                    # Update subscription template name
                    if self.pkg_subscription_template_id.name != vals['pkg_name']:
                        self.pkg_subscription_template_id.write({'name': vals['pkg_name']})
                        
                    # Update products linked to this template
                    for product in self.pkg_subscription_template_id.product_ids:
                        if product.name != vals['pkg_name']:
                            product.with_context(skip_saas_sync=True).write({'name': vals['pkg_name']})
                            
                    _logger.info(f"Synced name change from package {self.pkg_name} to template and products")
                except Exception as e:
                    _logger.warning(f"Failed to sync name changes for package {self.id}: {str(e)}")
            
            # Sync price changes
            if 'pkg_price' in vals and self.pkg_subscription_template_id:
                try:
                    # Update all products linked to this template
                    for product in self.pkg_subscription_template_id.product_ids:
                        if product.list_price != (vals['pkg_price'] or 0.0):
                            product.with_context(skip_saas_sync=True).write({'list_price': vals['pkg_price'] or 0.0})
                            
                    _logger.info(f"Synced price change from package {self.pkg_name} to products")
                except Exception as e:
                    _logger.warning(f"Failed to sync price changes for package {self.id}: {str(e)}")
        
        return result
    
    def action_view_saas_clients(self):
        """Open SaaS clients using this package."""
        action = self.env.ref('j_portainer_saas.action_saas_client').read()[0]
        action['domain'] = [('sc_package_id', '=', self.id)]
        action['context'] = {'default_sc_package_id': self.id}
        return action
