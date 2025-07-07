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
    
    This model defines SaaS packages with pricing and subscription management.
    Each package specifies billing information and warning delays for SaaS 
    client subscriptions.
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
        string='Sequence',
        readonly=True,
        copy=False,
        default=lambda self: _('New'),
        tracking=True,
        help='Auto-generated sequence code for package ordering (e.g., PK00001)'
    )
    
    pkg_name = fields.Char(
        string='Name',
        required=True,
        translate=True,
        tracking=True,
        help='Display name of the SaaS package'
    )
    
    pkg_warning_delay = fields.Integer(
        string='Warning Delay',
        default=7,
        required=True,
        tracking=True,
        help='Number of days before due date to send warning notifications'
    )
    
    pkg_mon_price = fields.Monetary(
        string='Monthly Price',
        currency_field='pkg_currency_id',
        tracking=True,
        help='Monthly subscription price for this package'
    )
    
    pkg_yea_price = fields.Monetary(
        string='Yearly Price',
        currency_field='pkg_currency_id',
        tracking=True,
        help='Yearly subscription price for this package'
    )
    
    pkg_has_free_trial = fields.Boolean(
        string='Has Free Trial',
        default=False,
        tracking=True,
        help='Enable free trial period for this package using configured interval days'
    )
    
    pkg_currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
        required=True,
        tracking=True,
        help='Currency for package pricing'
    )
    
    pkg_mon_subs_template_id = fields.Many2one(
        comodel_name='sale.subscription.template',
        string='Monthly Subscription Template',
        tracking=True,
        help='Associated monthly subscription template for billing and lifecycle management'
    )
    
    pkg_yea_subs_template_id = fields.Many2one(
        comodel_name='sale.subscription.template',
        string='Yearly Subscription Template',
        tracking=True,
        help='Associated yearly subscription template for billing and lifecycle management'
    )
    
    pkg_dns_domain_id = fields.Many2one(
        comodel_name='dns.domain',
        string='Domain',
        required=False,
        tracking=True,
        related='pkg_system_type_id.st_domain_id',
        help='The domain associated with this SaaS package for client deployments.'
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

    pkg_system_type_id = fields.Many2one(
        comodel_name='system.type',
        string='System Type',
        tracking=True,
        help='System type this package is designed for (e.g., Production, Development, Testing)'
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
    
    pkg_publish_website = fields.Boolean(
        string='Publish on Website',
        default=False,
        tracking=True,
        help='Indicates if this package should be displayed on the website'
    )
    
    pkg_feature_ids = fields.One2many(
        'saas.package.features',
        'pf_package_id',
        string='Package Features',
        help='List of features included in this package'
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
            'positive_warning_delay',
            'CHECK(pkg_warning_delay >= 0)',
            'Warning delay must be zero or positive.'
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
    
    @api.constrains('pkg_mon_price', 'pkg_yea_price')
    def _check_price_positive(self):
        """Validate that package prices are not negative."""
        for record in self:
            if record.pkg_mon_price and record.pkg_mon_price < 0:
                raise ValidationError(_('Monthly package price cannot be negative.'))
            if record.pkg_yea_price and record.pkg_yea_price < 0:
                raise ValidationError(_('Yearly package price cannot be negative.'))
    

    
    # ========================================================================
    # OVERRIDE METHODS
    # ========================================================================

    def write(self, vals):
        """Override write to sync changes to subscription template and product."""
        result = super().write(vals)

        # Extract template variables if docker_compose_template changed
        if 'pkg_docker_compose_template' in vals:
            self._extract_template_variables()

        # Sync name changes to both templates
        if 'pkg_name' in vals:
            try:
                # Update subscription template names (unless coming from template sync)
                if not self.env.context.get('skip_template_sync'):
                    for template_field in ['pkg_mon_subs_template_id', 'pkg_yea_subs_template_id']:
                        template = getattr(self, template_field, None)
                        if template and template.name != vals['pkg_name']:
                            template_suffix = 'Monthly' if 'mon' in template_field else 'Yearly'
                            template.write({'name': f"{vals['pkg_name']} ({template_suffix})"})

                # Update products linked to templates (unless coming from product sync)
                if not self.env.context.get('skip_product_sync'):
                    for template_field in ['pkg_mon_subs_template_id', 'pkg_yea_subs_template_id']:
                        template = getattr(self, template_field, None)
                        if template:
                            for product in template.product_ids:
                                if product.name != vals['pkg_name']:
                                    product.with_context(skip_saas_sync=True).write({'name': vals['pkg_name']})

                _logger.info(f"Synced name change from package {self.pkg_name} to templates and products")
            except Exception as e:
                _logger.warning(f"Failed to sync name changes for package {self.id}: {str(e)}")

        # Sync price changes to respective templates
        if any(field in vals for field in ['pkg_mon_price', 'pkg_yea_price']):
            try:
                # Update products linked to templates (unless coming from product sync)
                if not self.env.context.get('skip_product_sync'):
                    # Monthly price sync
                    if 'pkg_mon_price' in vals and self.pkg_mon_subs_template_id:
                        for product in self.pkg_mon_subs_template_id.product_ids:
                            if product.list_price != (vals['pkg_mon_price'] or 0.0):
                                product.with_context(skip_saas_sync=True).write({'list_price': vals['pkg_mon_price'] or 0.0})
                                _logger.info(f"Synced monthly price from package {self.pkg_name} to product {product.name}: {vals['pkg_mon_price']}")
                    
                    # Yearly price sync
                    if 'pkg_yea_price' in vals and self.pkg_yea_subs_template_id:
                        for product in self.pkg_yea_subs_template_id.product_ids:
                            if product.list_price != (vals['pkg_yea_price'] or 0.0):
                                product.with_context(skip_saas_sync=True).write({'list_price': vals['pkg_yea_price'] or 0.0})
                                _logger.info(f"Synced yearly price from package {self.pkg_name} to product {product.name}: {vals['pkg_yea_price']}")

                _logger.info(f"Synced price changes from package {self.pkg_name} to products")
            except Exception as e:
                _logger.warning(f"Failed to sync price changes for package {self.id}: {str(e)}")
        
        # Create subscription templates if prices are set but templates don't exist
        if any(field in vals for field in ['pkg_mon_price', 'pkg_yea_price']):
            self._create_subscription_templates()

        return result

    # ========================================================================
    # BUSINESS METHODS
    # ========================================================================
    
    @api.onchange('pkg_system_type_id')
    def _onchange_system_type_id(self):
        """Populate deployment template and variables from selected system type if they exist."""
        if self.pkg_system_type_id:
            # Copy template if it exists in system type
            if self.pkg_system_type_id.st_docker_compose_template:
                self.pkg_docker_compose_template = self.pkg_system_type_id.st_docker_compose_template
                
                # Copy template variables if they exist, avoiding duplicates
                if self.pkg_system_type_id.st_template_variable_ids:
                    # Get existing variable names to avoid duplicates
                    existing_var_names = set()
                    for existing_var in self.pkg_template_variable_ids:
                        if hasattr(existing_var, 'tv_variable_name') and existing_var.tv_variable_name:
                            existing_var_names.add(existing_var.tv_variable_name)
                    
                    # Build commands for only new variables
                    variable_commands = []
                    for st_var in self.pkg_system_type_id.st_template_variable_ids:
                        # Only add if variable doesn't already exist
                        if st_var.stv_variable_name and st_var.stv_variable_name not in existing_var_names:
                            variable_commands.append((0, 0, {
                                'tv_variable_name': st_var.stv_variable_name,
                                'tv_field_domain': st_var.stv_field_domain,
                                # tv_field_name will be computed automatically
                            }))
                    
                    # Apply commands only if there are new variables to add
                    if variable_commands:
                        self.pkg_template_variable_ids = variable_commands
            else:
                # Clear template and variables if system type has none
                self.pkg_docker_compose_template = False
                self.pkg_template_variable_ids = [(5, 0, 0)]
        else:
            # Clear template and variables if no system type selected
            self.pkg_docker_compose_template = False
            self.pkg_template_variable_ids = [(5, 0, 0)]
    
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
                    'tv_variable_name': var_name,
                    'tv_field_domain': '',
                    'tv_package_id': self.id,
                })

    def _create_subscription_templates(self):
        """Create monthly and yearly subscription templates if they don't exist."""
        for record in self:
            # Create monthly template if price is set but template doesn't exist
            if record.pkg_mon_price and not record.pkg_mon_subs_template_id:
                monthly_template = self.env['sale.subscription.template'].with_context(
                    from_saas_package=True,
                    saas_package_id=record.id,
                    saas_package_name=record.pkg_name,
                    saas_package_price=record.pkg_mon_price,
                    saas_package_period='monthly'
                ).create({
                    'name': f"{record.pkg_name} (Monthly)",
                    'code': f"{record.pkg_sequence}-M",
                    'recurring_rule_type': 'months',
                    'recurring_interval': 1,
                    'is_saas_template': True,
                })
                record.pkg_mon_subs_template_id = monthly_template.id
                _logger.info(f"Package {record.pkg_name}: Created MONTHLY template {monthly_template.id} with rule_type '{monthly_template.recurring_rule_type}' assigned to pkg_mon_subs_template_id")
                
                # Create monthly product with proper name and properties
                monthly_product = self.env['product.template'].with_context(
                    from_saas_package=True,
                    saas_package_id=record.id,
                    saas_package_period='monthly'
                ).create({
                    'name': f"{record.pkg_name} (Monthly)",
                    'list_price': record.pkg_mon_price,
                    'detailed_type': 'service',
                    'is_saas_product': True,
                    'subscribable': True,
                    'subscription_template_id': monthly_template.id,
                })
                
                # Link product to template
                monthly_template.write({'product_ids': [(4, monthly_product.id)]})
            
            # Create yearly template if price is set but template doesn't exist
            if record.pkg_yea_price and not record.pkg_yea_subs_template_id:
                yearly_template = self.env['sale.subscription.template'].with_context(
                    from_saas_package=True,
                    saas_package_id=record.id,
                    saas_package_name=record.pkg_name,
                    saas_package_price=record.pkg_yea_price,
                    saas_package_period='yearly'
                ).create({
                    'name': f"{record.pkg_name} (Yearly)",
                    'code': f"{record.pkg_sequence}-Y",
                    'recurring_rule_type': 'years',
                    'recurring_interval': 1,
                    'is_saas_template': True,
                })
                record.pkg_yea_subs_template_id = yearly_template.id
                _logger.info(f"Package {record.pkg_name}: Created YEARLY template {yearly_template.id} with rule_type '{yearly_template.recurring_rule_type}' assigned to pkg_yea_subs_template_id")
                
                # Create yearly product with proper name and properties
                yearly_product = self.env['product.template'].with_context(
                    from_saas_package=True,
                    saas_package_id=record.id,
                    saas_package_period='yearly'
                ).create({
                    'name': f"{record.pkg_name} (Yearly)",
                    'list_price': record.pkg_yea_price,
                    'detailed_type': 'service',
                    'is_saas_product': True,
                    'subscribable': True,
                    'subscription_template_id': yearly_template.id,
                })
                
                # Link product to template
                yearly_template.write({'product_ids': [(4, yearly_product.id)]})

    def name_get(self):
        """Return package name with pricing information."""
        result = []
        for record in self:
            name = record.pkg_name
            if record.pkg_currency_id:
                prices = []
                if record.pkg_mon_price:
                    prices.append(f"M:{record.pkg_currency_id.symbol}{record.pkg_mon_price:.2f}")
                if record.pkg_yea_price:
                    prices.append(f"Y:{record.pkg_currency_id.symbol}{record.pkg_yea_price:.2f}")
                if prices:
                    name = f"{name} ({', '.join(prices)})"
            result.append((record.id, name))
        return result
    
    @api.model
    def create(self, vals):
        """Override create to generate sequence number and create subscription template."""
        if vals.get('pkg_sequence', 'New') == 'New':
            vals['pkg_sequence'] = self.env['ir.sequence'].next_by_code('saas.package')
        
        package = super().create(vals)
        
        # Extract template variables if docker_compose_template is provided
        if vals.get('docker_compose_template'):
            package._extract_template_variables()
        
        # Create subscription templates if prices are provided
        if vals.get('pkg_mon_price') or vals.get('pkg_yea_price'):
            package._create_subscription_templates()

        return package

    def action_view_saas_clients(self):
        """Open SaaS clients using this package."""
        action = self.env.ref('j_portainer_saas.action_saas_client').read()[0]
        action['domain'] = [('sc_package_id', '=', self.id)]
        action['context'] = {'default_sc_package_id': self.id}
        return action

