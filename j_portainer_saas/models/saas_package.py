#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging
import re

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
    
    pkg_currency_id = fields.Many2one(
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
    
    pkg_docker_compose_template = fields.Text(
        string='Docker Compose Template',
        help='Docker Compose content with variables marked as @VARIABLE_NAME@'
    )
    
    pkg_template_variable_ids = fields.One2many(
        comodel_name='saas.template.variable',
        inverse_name='tv_package_id',
        string='Template Variables',
        help='Auto-extracted variables from Docker Compose template'
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
    # OVERRIDE METHODS
    # ========================================================================

    def write(self, vals):
        """Override write to sync changes to subscription template and product."""
        result = super().write(vals)

        # Extract template variables if docker_compose_template changed
        if 'pkg_docker_compose_template' in vals:
            self._extract_template_variables()

        # Sync name changes
        if 'pkg_name' in vals and self.pkg_subscription_template_id:
            try:
                # Update subscription template name (unless coming from template sync)
                if not self.env.context.get('skip_template_sync'):
                    if self.pkg_subscription_template_id.name != vals['pkg_name']:
                        self.pkg_subscription_template_id.write({'name': vals['pkg_name']})

                # Update products linked to this template (unless coming from product sync)
                if not self.env.context.get('skip_product_sync'):
                    for product in self.pkg_subscription_template_id.product_ids:
                        if product.name != vals['pkg_name']:
                            product.with_context(skip_saas_sync=True).write({'name': vals['pkg_name']})

                _logger.info(f"Synced name change from package {self.pkg_name} to template and products")
            except Exception as e:
                _logger.warning(f"Failed to sync name changes for package {self.id}: {str(e)}")

        # Sync price changes
        if 'pkg_price' in vals and self.pkg_subscription_template_id:
            try:
                # Update all products linked to this template (unless coming from product sync)
                if not self.env.context.get('skip_product_sync'):
                    for product in self.pkg_subscription_template_id.product_ids:
                        if product.list_price != (vals['pkg_price'] or 0.0):
                            product.with_context(skip_saas_sync=True).write({'list_price': vals['pkg_price'] or 0.0})

                _logger.info(f"Synced price change from package {self.pkg_name} to products")
            except Exception as e:
                _logger.warning(f"Failed to sync price changes for package {self.id}: {str(e)}")

        return result

    # ========================================================================
    # BUSINESS METHODS
    # ========================================================================
    
    @api.onchange('pkg_docker_compose_template')
    def _onchange_docker_compose_template(self):
        """Extract variables from Docker Compose template when content changes.
        Only adds new variables and removes specific deleted ones - NEVER recreates all."""
        
        if not self.pkg_docker_compose_template:
            # Clear all variables if template is empty
            self.pkg_template_variable_ids = [(5, 0, 0)]
            return
        
        # Find all @VARIABLE_NAME@ patterns in template
        variable_pattern = r'@(\w+)@'
        template_variables = set(re.findall(variable_pattern, self.pkg_docker_compose_template))
        
        # Get existing variable names
        existing_var_names = set()
        for var in self.pkg_template_variable_ids:
            if hasattr(var, 'tv_variable_name') and var.tv_variable_name:
                existing_var_names.add(var.tv_variable_name)
        
        # Calculate what needs to be added or removed
        variables_to_add = template_variables - existing_var_names
        variables_to_remove = existing_var_names - template_variables
        print('variables_to_remove', variables_to_remove)
        # Build command list for ONLY the changes needed
        commands = []
        
        # Step 1: Remove ONLY variables no longer in template
        for var in self.pkg_template_variable_ids:
            if hasattr(var, 'tv_variable_name') and var.tv_variable_name in variables_to_remove:
                # Remove saved variable by ID
                commands.append((2, var.id, 0))
                # Unsaved variables will be automatically excluded from new list
        
        # Step 2: Add ONLY new variables
        for var_name in variables_to_add:
            commands.append((0, 0, {
                'tv_variable_name': var_name,
                'tv_field_domain': '',
                'tv_field_name': '',
            }))
        
        # Apply changes only if there are actual additions or removals
        if commands:
            self.pkg_template_variable_ids = commands
    
    def _extract_template_variables(self):
        """Extract @VARIABLE_NAME@ patterns from Docker Compose template."""
        if not self.pkg_docker_compose_template:
            # Clear all variables if template is empty
            self.pkg_template_variable_ids.unlink()
            return
        
        # Find all @VARIABLE_NAME@ patterns
        variable_pattern = r'@(\w+)@'
        variables = set(re.findall(variable_pattern, self.pkg_docker_compose_template))
        
        # Get existing variables
        existing_variables = {var.tv_variable_name for var in self.pkg_template_variable_ids}
        
        # Remove variables no longer in template
        variables_to_remove = existing_variables - variables
        if variables_to_remove:
            variables_to_delete = self.pkg_template_variable_ids.filtered(
                lambda v: v.tv_variable_name in variables_to_remove
            )
            variables_to_delete.unlink()
        
        # Add new variables
        variables_to_add = variables - existing_variables
        for var_name in variables_to_add:
            if var_name:  # Ensure variable name is not empty
                self.env['saas.template.variable'].create({
                    'variable_name': var_name,
                    'field_domain': '',
                    'package_id': self.id,
                })

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
        
        package = super().create(vals)
        
        # Extract template variables if docker_compose_template is provided
        if vals.get('docker_compose_template'):
            package._extract_template_variables()
        
        # Link SaaS products to this package if template has products
        if package.pkg_subscription_template_id and package.pkg_subscription_template_id.product_ids:
            template = package.pkg_subscription_template_id
            # Update SaaS products to link back to this package
            for product in template.product_ids:
                if product.is_saas_product and not product.saas_package_id:
                    product.write({'saas_package_id': package.id})
                    _logger.info(f"Linked SaaS product {product.name} to package {package.pkg_name}")

        return package

    def action_view_saas_clients(self):
        """Open SaaS clients using this package."""
        action = self.env.ref('j_portainer_saas.action_saas_client').read()[0]
        action['domain'] = [('sc_package_id', '=', self.id)]
        action['context'] = {'default_sc_package_id': self.id}
        return action

