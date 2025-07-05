#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request
import json


class SaaSWebController(http.Controller):
    """
    Controller for handling SaaS web operations and snippet data
    
    This controller provides endpoints for:
    - Fetching package data for the pricing snippet
    - Handling package selection and cart operations
    - Managing free trial requests
    """

    @http.route('/saas/packages/data', type='json', auth='public', methods=['POST'], csrf=False)
    def get_packages_data(self):
        """
        Fetch all active SaaS packages for the pricing snippet
        
        Returns:
            dict: JSON response containing package data with pricing info
        """
        try:
            # Check if saas.package model exists
            if 'saas.package' not in request.env:
                return {
                    'success': False,
                    'error': 'SaaS package model not found. Please ensure j_portainer_saas module is installed.'
                }
            
            # Get all active packages
            packages = request.env['saas.package'].sudo().search([
                ('pkg_active', '=', True)
            ])
            
            # Prepare packages data
            packages_data = []
            for package in packages:
                # Calculate yearly price (assume 10% discount for yearly billing)
                monthly_price = package.pkg_price or 0
                yearly_price = monthly_price * 12 * 0.9  # 10% discount
                
                package_data = {
                    'id': package.id,
                    'name': package.pkg_name,
                    'description': package.pkg_description or '',
                    'monthly_price': monthly_price,
                    'yearly_price': yearly_price,
                    'currency_symbol': package.pkg_currency_id.symbol if package.pkg_currency_id else '$',
                    'has_free_trial': package.pkg_has_free_trial,
                    'subscription_period': package.pkg_subscription_period,
                    'features': self._get_package_features(package),
                }
                packages_data.append(package_data)
            
            return {
                'success': True,
                'packages': packages_data,
                'free_trial_days': self._get_free_trial_days(),
                'debug': f'Found {len(packages)} packages'
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'debug': f'Exception in get_packages_data: {type(e).__name__}'
            }

    def _get_package_features(self, package):
        """
        Extract package features from description or template variables
        
        Args:
            package: SaaS package record
            
        Returns:
            list: List of feature strings
        """
        features = []
        
        # Extract features from description if available
        if package.pkg_description:
            # Simple feature extraction - split by newlines and clean up
            lines = package.pkg_description.split('\n')
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#'):
                    features.append(line)
        
        # Add template variables as features
        if package.pkg_template_variable_ids:
            for var in package.pkg_template_variable_ids:
                if var.tv_variable_name:
                    features.append(f"Configurable {var.tv_variable_name}")
        
        # Default features if none found
        if not features:
            features = [
                f"{package.pkg_system_type_id.name or 'System'} Access",
                "24/7 Support",
                "Regular Updates",
                "Secure Hosting"
            ]
        
        return features[:4]  # Limit to 4 features for clean display

    def _get_free_trial_days(self):
        """
        Get the configured free trial days from settings
        
        Returns:
            int: Number of free trial days
        """
        try:
            config = request.env['ir.config_parameter'].sudo()
            return int(config.get_param('j_portainer_saas.free_trial_interval_days', 30))
        except:
            return 30

    @http.route('/saas/package/select', type='json', auth='public', methods=['POST'], csrf=False)
    def select_package(self, package_id, billing_period='monthly', free_trial=False):
        """
        Handle package selection (placeholder for future implementation)
        
        Args:
            package_id (int): Selected package ID
            billing_period (str): 'monthly' or 'yearly'
            free_trial (bool): Whether free trial is requested
            
        Returns:
            dict: Response with next steps
        """
        return {
            'success': True,
            'message': 'Package selection functionality will be implemented in future updates',
            'package_id': package_id,
            'billing_period': billing_period,
            'free_trial': free_trial,
        }

    @http.route('/saas/packages/demo', type='http', auth='public', methods=['POST', 'GET'], csrf=False)
    def get_demo_packages(self):
        """
        Return demo packages for testing the snippet functionality
        
        Returns:
            JSON response containing demo package data
        """
        demo_packages = [
            {
                'id': 1,
                'name': 'Starter',
                'description': 'Perfect for small teams getting started',
                'monthly_price': 29.0,
                'yearly_price': 261.0,  # 10% discount
                'currency_symbol': '$',
                'has_free_trial': True,
                'subscription_period': 'monthly',
                'features': [
                    '5 Projects',
                    '10GB Storage',
                    'Email Support',
                    'Basic Analytics'
                ]
            },
            {
                'id': 2,
                'name': 'Professional',
                'description': 'For growing businesses with advanced needs',
                'monthly_price': 79.0,
                'yearly_price': 711.0,  # 10% discount
                'currency_symbol': '$',
                'has_free_trial': True,
                'subscription_period': 'monthly',
                'features': [
                    '25 Projects',
                    '100GB Storage',
                    'Priority Support',
                    'Advanced Analytics'
                ]
            },
            {
                'id': 3,
                'name': 'Enterprise',
                'description': 'For large organizations with complex requirements',
                'monthly_price': 199.0,
                'yearly_price': 1791.0,  # 10% discount
                'currency_symbol': '$',
                'has_free_trial': False,
                'subscription_period': 'monthly',
                'features': [
                    'Unlimited Projects',
                    '1TB Storage',
                    'Dedicated Support',
                    'Custom Analytics'
                ]
            }
        ]
        
        response_data = {
            'success': True,
            'packages': demo_packages,
            'free_trial_days': 30,
            'debug': 'Demo data returned'
        }
        
        return request.make_response(
            json.dumps(response_data),
            headers=[('Content-Type', 'application/json')]
        )