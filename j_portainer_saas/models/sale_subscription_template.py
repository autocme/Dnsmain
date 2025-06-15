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
    saas_package_ids = fields.One2many(
        comodel_name='saas.package',
        inverse_name='pkg_subscription_template_id',
        string='SaaS Packages',
        help='SaaS packages that use this subscription template'
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

    @api.depends('saas_package_ids')
    def _compute_saas_package_count(self):
        """Compute the number of SaaS packages using this template."""
        for record in self:
            record.saas_package_count = len(record.saas_package_ids)

    @api.model
    def create(self, vals):
        """Override create to handle SaaS package-triggered template creation."""
        template = super().create(vals)

        # Check if template created from SaaS package context
        if self.env.context.get('from_saas_package'):
            package_id = self.env.context.get('saas_package_id')
            package_name = self.env.context.get('saas_package_name')
            package_price = self.env.context.get('saas_package_price', 0.0)

            if package_id and package_name:
                # Mark as SaaS template
                template.write({'is_saas_template': True})

                # Create product for this template
                product_vals = {
                    'name': package_name,
                    'type': 'service',
                    'subscribable': True,
                    'list_price': package_price,
                    'sale_ok': True,
                    'purchase_ok': False,
                    'subscription_template_id': template.id,
                    'categ_id': self.env.ref('product.product_category_all').id,
                }

                try:
                    product = self.env['product.template'].create(product_vals)
                    _logger.info(f"Created product {product.name} for SaaS template {template.name}")

                    # Link template back to package
                    package = self.env['saas.package'].browse(package_id)
                    package.write({'pkg_subscription_template_id': template.id})
                    _logger.info(f"Linked template {template.name} to SaaS package {package.pkg_name}")

                except Exception as e:
                    _logger.error(f"Failed to create product or link template for SaaS package {package_id}: {str(e)}")

        return template

    def write(self, vals):
        """Override write to sync changes with SaaS packages."""
        result = super().write(vals)
        
        # Sync name changes to linked SaaS packages
        if 'name' in vals:
            for record in self:
                if record.is_saas_template and record.saas_package_ids:
                    try:
                        # Update SaaS package names if needed
                        for package in record.saas_package_ids:
                            if package.pkg_name != vals['name']:
                                package.write({'pkg_name': vals['name']})
                        
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
        action['domain'] = [('pkg_subscription_template_id', '=', self.id)]
        action['context'] = {'default_pkg_subscription_template_id': self.id}
        return action

    def unlink(self):
        """Override unlink to check SaaS package dependencies."""
        for record in self:
            if record.is_saas_template and record.saas_package_ids:
                # Update linked packages to remove template reference
                record.saas_package_ids.write({'pkg_subscription_template_id': False})
                _logger.info(f"Removed template reference from {len(record.saas_package_ids)} SaaS packages")
        
        return super().unlink()
