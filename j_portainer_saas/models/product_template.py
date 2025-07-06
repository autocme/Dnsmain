#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import api, fields, models
import logging

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    """
    Inheritance of Product Template for SaaS Package Integration
    
    This model extends the base product template to integrate with SaaS packages,
    ensuring all product modifications related to subscriptions are handled 
    through the j_portainer_saas module.
    """
    _inherit = 'product.template'

    # Add SaaS-specific fields
    is_saas_product = fields.Boolean(
        string='Is SaaS Product',
        default=False,
        help='Indicates if this product is created for SaaS packages'
    )
    
    saas_package_id = fields.Many2one(
        comodel_name='saas.package',
        string='SaaS Package',
        help='The SaaS package that this product represents'
    )

    @api.model
    def create(self, vals):
        """Override create to handle SaaS package-triggered product creation."""
        product = super().create(vals)
        
        # Check if product created from SaaS context
        if self.env.context.get('from_saas_package'):
            package_id = self.env.context.get('saas_package_id')
            
            if package_id:
                # Mark as SaaS product and link to package
                product.write({
                    'is_saas_product': True,
                    'saas_package_id': package_id
                })
                
                _logger.info(f"Created SaaS product {product.name} for package {package_id}")
        
        return product

    def write(self, vals):
        """Override write to sync changes with SaaS packages when applicable."""
        result = super().write(vals)
        
        # Only sync if not coming from SaaS package sync to avoid infinite loops
        if not self.env.context.get('skip_saas_sync'):
            # Sync price changes back to SaaS package if this is a SaaS product
            if 'list_price' in vals:
                for record in self:
                    if record.is_saas_product and record.subscription_template_id:
                        try:
                            # Get the subscription template to determine billing period
                            template = record.subscription_template_id
                            new_price = vals['list_price']
                            
                            # Find the package that uses this template
                            package = None
                            price_field = None
                            
                            # Check if this template is used for monthly billing
                            if template.recurring_rule_type == 'months':
                                # Find package that has this template as monthly template
                                monthly_packages = self.env['saas.package'].search([
                                    ('pkg_mon_subs_template_id', '=', template.id)
                                ])
                                if monthly_packages:
                                    package = monthly_packages[0]
                                    price_field = 'pkg_mon_price'
                                    billing_type = 'monthly'
                            
                            # Check if this template is used for yearly billing
                            elif template.recurring_rule_type == 'years':
                                # Find package that has this template as yearly template
                                yearly_packages = self.env['saas.package'].search([
                                    ('pkg_yea_subs_template_id', '=', template.id)
                                ])
                                if yearly_packages:
                                    package = yearly_packages[0]
                                    price_field = 'pkg_yea_price'
                                    billing_type = 'yearly'
                            
                            # Update the package price if we found the right package and field
                            if package and price_field:
                                current_price = getattr(package, price_field, 0.0)
                                if current_price != new_price:
                                    package.with_context(skip_product_sync=True).write({
                                        price_field: new_price
                                    })
                                    _logger.info(f"Synced {billing_type} price change from product {record.name} (template: {template.name}) to SaaS package {package.pkg_name}.{price_field}")
                            else:
                                _logger.warning(f"Could not determine package or price field for product {record.name} with template {template.name} (rule_type: {template.recurring_rule_type})")
                                
                        except Exception as e:
                            _logger.warning(f"Failed to sync price change to SaaS package: {str(e)}")
            
            # Sync name changes to related subscription template if this is a SaaS product
            if 'name' in vals:
                for record in self:
                    if record.is_saas_product and record.subscription_template_id:
                        try:
                            # Update the subscription template name to match the product name
                            # This maintains consistency between product and template naming
                            if record.subscription_template_id.name != vals['name']:
                                record.subscription_template_id.with_context(skip_product_sync=True).write({
                                    'name': vals['name']
                                })
                                _logger.info(f"Synced name change from product {record.name} to subscription template {record.subscription_template_id.name}")
                        except Exception as e:
                            _logger.warning(f"Failed to sync name change to subscription template: {str(e)}")
        
        return result

    def action_view_saas_package(self):
        """Action to view the associated SaaS package."""
        self.ensure_one()
        
        if not self.saas_package_id:
            return False
        
        return {
            'name': 'SaaS Package',
            'type': 'ir.actions.act_window',
            'res_model': 'saas.package',
            'res_id': self.saas_package_id.id,
            'view_mode': 'form',
            'target': 'current',
        }