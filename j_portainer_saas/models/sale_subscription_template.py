#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import api, fields, models
import logging

_logger = logging.getLogger(__name__)


class SaleSubscriptionTemplate(models.Model):
    """
    Inheritance of Sale Subscription Template for SaaS Package Integration
    
    This model extends the base subscription template to integrate with SaaS packages,
    ensuring all subscription template modifications are handled through the 
    j_portainer_saas module rather than directly modifying the base subscription_oca module.
    """
    _inherit = 'sale.subscription.template'

    # Add SaaS-specific fields
    saas_monthly_package_ids = fields.One2many(
        comodel_name='saas.package',
        inverse_name='pkg_mon_subs_template_id',
        string='SaaS Packages (Monthly)',
        help='SaaS packages that use this template for monthly billing'
    )
    
    saas_yearly_package_ids = fields.One2many(
        comodel_name='saas.package',
        inverse_name='pkg_yea_subs_template_id',
        string='SaaS Packages (Yearly)',
        help='SaaS packages that use this template for yearly billing'
    )
    
    is_saas_template = fields.Boolean(
        string='Is SaaS Template',
        default=False,
        help='Indicates if this template is used for SaaS packages'
    )
    
    saas_package_count = fields.Integer(
        compute='_compute_saas_package_count',
        string='SaaS Package Count'
    )

    @api.depends('saas_monthly_package_ids', 'saas_yearly_package_ids')
    def _compute_saas_package_count(self):
        """Compute the number of SaaS packages using this template."""
        for record in self:
            record.saas_package_count = len(record.saas_monthly_package_ids) + len(record.saas_yearly_package_ids)

    @api.model
    def create(self, vals):
        """Override create to handle SaaS package-triggered template creation."""
        # Check if template created from SaaS package context
        if self.env.context.get('from_saas_package'):
            package_name = self.env.context.get('saas_package_name')
            package_period = self.env.context.get('saas_package_period', 'monthly')
            print('package_period ........', package_period)
            recurring_rule_type = 'monthly' if package_period == 'months' else 'years'

            if package_name:
                vals['name'] = package_name
            if recurring_rule_type:
                vals['recurring_rule_type'] = recurring_rule_type
            # Mark as SaaS template
            vals['is_saas_template'] = True
        
        # Create the template first
        template = super().create(vals)
        
        # Create product after template is created (if from SaaS context)
        if self.env.context.get('from_saas_package'):
            package_name = self.env.context.get('saas_package_name')
            package_price = self.env.context.get('saas_package_price', 0.0)
            
            if package_name:
                product_values = {
                    'name': package_name,
                    'list_price': package_price,
                    'detailed_type': 'service',
                    'subscribable': True,
                    'subscription_template_id': template.id,
                    'is_saas_product': True,
                }
                
                product = self.env['product.template'].create(product_values)
                _logger.info(f"Created SaaS product {product.name} for template {template.name}")
        
        return template

    def write(self, vals):
        """Override write to sync changes with SaaS packages."""
        result = super().write(vals)
        
        # Sync name changes to linked SaaS packages
        if 'name' in vals:
            for record in self:
                if record.is_saas_template:
                    try:
                        # Get all packages using this template (monthly or yearly)
                        all_packages = record.saas_monthly_package_ids + record.saas_yearly_package_ids
                        
                        # Update SaaS package names if needed
                        for package in all_packages:
                            base_name = vals['name'].replace(' (Monthly)', '').replace(' (Yearly)', '')
                            if package.pkg_name != base_name:
                                package.write({'pkg_name': base_name})
                        
                        # Update product names
                        for product in record.product_ids:
                            if product.name != vals['name']:
                                product.write({'name': vals['name']})
                                
                    except Exception as e:
                        _logger.warning(f"Failed to sync name changes for SaaS template {record.id}: {str(e)}")
        
        return result

    def action_view_saas_packages(self):
        """Action to view SaaS packages using this template."""
        action = self.env.ref('j_portainer_saas.action_saas_package').read()[0]
        action['domain'] = ['|', ('pkg_mon_subs_template_id', '=', self.id), ('pkg_yea_subs_template_id', '=', self.id)]
        action['context'] = {}
        return action

    def unlink(self):
        """Override unlink to check SaaS package dependencies."""
        for record in self:
            if record.is_saas_template and record.saas_package_ids:
                # Update linked packages to remove template reference
                record.saas_package_ids.write({'pkg_subscription_template_id': False})
                _logger.info(f"Removed template reference from {len(record.saas_package_ids)} SaaS packages")
        
        return super().unlink()
