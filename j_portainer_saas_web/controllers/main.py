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

    @http.route('/saas/packages/data', type='http', auth='public', methods=['POST', 'GET'], csrf=False)
    def get_packages_data(self):
        """
        Fetch all active SaaS packages for the pricing snippet
        
        Returns:
            JSON response containing package data with pricing info
        """
        try:
            # Check if saas.package model exists
            if 'saas.package' not in request.env:
                response_data = {
                    'success': False,
                    'error': 'SaaS package model not found. Please ensure j_portainer_saas module is installed.',
                    'debug': 'Missing j_portainer_saas module - model saas.package not found'
                }
                return request.make_response(
                    json.dumps(response_data),
                    headers=[('Content-Type', 'application/json')]
                )
            
            # Get all packages published on website
            packages = request.env['saas.package'].sudo().search([
                ('pkg_active', '=', True),
                ('pkg_publish_website', '=', True)
            ])
            
            # If no packages found, return error to force demo fallback
            if not packages:
                response_data = {
                    'success': False,
                    'error': 'No published packages found in database',
                    'debug': 'Database query returned 0 packages with pkg_active=True and pkg_publish_website=True'
                }
                return request.make_response(
                    json.dumps(response_data),
                    headers=[('Content-Type', 'application/json')]
                )
            
            # Prepare packages data
            packages_data = []
            for package in packages:
                # Use the new monthly and yearly price fields
                monthly_price = package.pkg_mon_price or 0
                yearly_price = package.pkg_yea_price or 0
                
                package_data = {
                    'id': package.id,
                    'name': package.pkg_name,
                    'description': package.pkg_description or '',
                    'monthly_price': monthly_price,
                    'yearly_price': yearly_price,
                    'currency_symbol': package.pkg_currency_id.symbol if package.pkg_currency_id else '$',
                    'has_free_trial': package.pkg_has_free_trial,
                    'monthly_active': package.pkg_monthly_active,
                    'yearly_active': package.pkg_yearly_active,
                    'features': self._get_package_features(package),
                }
                packages_data.append(package_data)
            
            response_data = {
                'success': True,
                'packages': packages_data,
                'free_trial_days': self._get_free_trial_days(),
                'debug': f'Successfully loaded {len(packages)} real packages from database'
            }
            
            return request.make_response(
                json.dumps(response_data),
                headers=[('Content-Type', 'application/json')]
            )
            
        except Exception as e:
            response_data = {
                'success': False,
                'error': str(e),
                'debug': f'Exception in get_packages_data: {type(e).__name__}'
            }
            return request.make_response(
                json.dumps(response_data),
                headers=[('Content-Type', 'application/json')]
            )

    def _get_package_features(self, package):
        """
        Extract package features from package features model, description or template variables
        
        Args:
            package: SaaS package record
            
        Returns:
            list: List of feature strings
        """
        features = []
        
        # Get features from package features model (priority 1)
        if package.pkg_feature_ids:
            for feature in package.pkg_feature_ids:
                if feature.pf_name:
                    features.append(feature.pf_name)
        
        # Extract features from description if no features model data (priority 2)
        if not features and package.pkg_description:
            # Simple feature extraction - split by newlines and clean up
            lines = package.pkg_description.split('\n')
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#'):
                    features.append(line)
        
        # Add template variables as features if still no features (priority 3)
        if not features and package.pkg_template_variable_ids:
            for var in package.pkg_template_variable_ids:
                if var.tv_variable_name:
                    features.append(f"Configurable {var.tv_variable_name}")
        
        # Default features if none found (priority 4)
        if not features:
            system_type_name = 'System'
            if package.pkg_system_type_id:
                system_type_name = package.pkg_system_type_id.st_complete_name or package.pkg_system_type_id.st_name or 'System'
            
            features = [
                f"{system_type_name} Access",
                "24/7 Support",
                "Regular Updates",
                "Secure Hosting"
            ]
        
        return features  # Return all features without limiting

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

    @http.route('/saas/purchase/confirm', type='http', website=True, auth='user', methods=['GET'], csrf=False)
    def purchase_confirm(self, package_id, billing_cycle='monthly', is_free_trial='false', **kwargs):
        """
        Display purchase confirmation page with package details and legal agreement
        
        Args:
            package_id (str): Selected package ID
            billing_cycle (str): 'monthly' or 'yearly'
            is_free_trial (str): 'true' or 'false'
            
        Returns:
            Rendered confirmation template
        """
        try:
            # Convert string parameters to appropriate types
            package_id = int(package_id)
            is_free_trial = str(is_free_trial).lower() == 'true'
            
            # Debug logging for parameter conversion
            _logger.info(f"Purchase Confirm: package_id={package_id}, billing_cycle='{billing_cycle}', is_free_trial_param='{is_free_trial}' (original), is_free_trial_converted={is_free_trial}")
            
            # Get the package
            package = request.env['saas.package'].sudo().browse(package_id)
            if not package.exists() or not package.pkg_active:
                return request.render('j_portainer_saas_web.purchase_error', {
                    'error_message': 'Package not found or not available'
                })
            
            # Validate free trial request
            if is_free_trial and not package.pkg_has_free_trial:
                return request.render('j_portainer_saas_web.purchase_error', {
                    'error_message': 'Free trial is not available for this package'
                })
            
            # Get pricing information
            price = package.pkg_mon_price if billing_cycle == 'monthly' else package.pkg_yea_price
            currency_symbol = package.pkg_currency_id.symbol if package.pkg_currency_id else '$'
            
            # Handle None price values
            if price is None:
                price = 0.0
            
            # Prepare template data
            template_data = {
                'package': package,
                'billing_cycle': billing_cycle,
                'is_free_trial': is_free_trial,
                'price': price,
                'currency_symbol': currency_symbol,
                'period_text': 'month' if billing_cycle == 'monthly' else 'year',
                'free_trial_days': self._get_free_trial_days(),
            }
            
            # Log template data for debugging
            import logging
            _logger = logging.getLogger(__name__)
            _logger.info(f"Purchase Confirm Template Data: package_id={package.id}, billing_cycle='{billing_cycle}', is_free_trial={is_free_trial}, price={price}")
            
            return request.render('j_portainer_saas_web.purchase_confirm', template_data)
            
        except Exception as e:
            return request.render('j_portainer_saas_web.purchase_error', {
                'error_message': f'Error loading confirmation page: {str(e)}'
            })

    @http.route('/saas/package/purchase', type='json', auth='user', methods=['POST'], csrf=False)
    def purchase_package(self, package_id, billing_cycle='monthly', is_free_trial=False, **kwargs):
        """
        Purchase a SaaS package and create a SaaS client
        
        Args:
            package_id (int): Selected package ID
            billing_cycle (str): 'monthly' or 'yearly'
            is_free_trial (bool): Whether this is a free trial request
            
        Returns:
            dict: Response with creation status and redirect URL
        """
        try:
            # Log the incoming request for debugging
            import logging
            _logger = logging.getLogger(__name__)
            _logger.info(f"Website Purchase Request: package_id={package_id}, billing_cycle='{billing_cycle}', is_free_trial={is_free_trial}, kwargs={kwargs}")
            
            # Validate package_id parameter
            if package_id is None:
                _logger.error("Package ID is None")
                return {
                    'success': False,
                    'error': 'Package ID is required'
                }
            
            # Validate billing cycle parameter
            if billing_cycle not in ['monthly', 'yearly']:
                _logger.warning(f"Invalid billing_cycle '{billing_cycle}', defaulting to 'monthly'")
                billing_cycle = 'monthly'
            
            # Check if user is logged in
            if not request.env.user or request.env.user._is_public():
                return {
                    'success': False,
                    'error': 'User must be logged in to purchase a package',
                    'redirect_login': True
                }
            
            # Get the package
            try:
                package_id_int = int(package_id)
            except (ValueError, TypeError) as e:
                _logger.error(f"Invalid package_id format: {package_id}, error: {e}")
                return {
                    'success': False,
                    'error': f'Invalid package ID format: {package_id}'
                }
            
            package = request.env['saas.package'].sudo().browse(package_id_int)
            if not package.exists():
                return {
                    'success': False,
                    'error': 'Package not found'
                }
            
            if not package.pkg_active:
                return {
                    'success': False,
                    'error': 'Package is not available for purchase'
                }
            
            # Get user's partner
            partner = request.env.user.partner_id
            
            # Validate free trial request
            if is_free_trial and not package.pkg_has_free_trial:
                return {
                    'success': False,
                    'error': 'Free trial is not available for this package'
                }
            
            # Create SaaS client with draft status
            client_vals = {
                'sc_partner_id': partner.id,
                'sc_package_id': package.id,
                'sc_status': 'draft',
                'sc_subscription_period': billing_cycle,
                'sc_is_free_trial': is_free_trial,
            }
            
            # Debug logging for client creation
            _logger.info(f"Creating SaaS client with values: {client_vals}")
            
            saas_client = request.env['saas.client'].sudo().create(client_vals)
            
            # Log the purchase details for debugging
            _logger.info(f"Website Purchase: Created SaaS client {saas_client.id} with billing_cycle='{billing_cycle}', sc_subscription_period='{saas_client.sc_subscription_period}', is_free_trial={is_free_trial}, sc_is_free_trial={saas_client.sc_is_free_trial}")
            
            # Deploy the client ONLY if it's a free trial
            if is_free_trial:
                try:
                    # Deploy the free trial client
                    saas_client.action_deploy_client()
                    _logger.info(f"Free trial client {saas_client.id} deployment started")
                except Exception as e:
                    _logger.warning(f"Failed to deploy free trial client {saas_client.id}: {e}")
            
            # Get invoice portal URL for paid packages (invoice already created by base module)
            invoice_portal_url = None
            if not is_free_trial and saas_client.sc_subscription_id:
                try:
                    # Get the latest invoice from the subscription
                    invoices = saas_client.sc_subscription_id.invoice_ids
                    if invoices:
                        latest_invoice = invoices[-1]  # Get the most recent invoice
                        invoice_portal_url = f"/my/invoices/{latest_invoice.id}"
                        _logger.info(f"Found invoice {latest_invoice.id} for paid client {saas_client.id}")
                except Exception as e:
                    _logger.warning(f"Failed to get invoice for paid client {saas_client.id}: {e}")
            
            # Get client full domain for redirect (clean domain without server prefix)
            client_domain = '/web'
            if saas_client.sc_full_domain:
                # Extract clean domain from full domain (remove any server prefix)
                full_domain = saas_client.sc_full_domain
                if full_domain.startswith('http://') or full_domain.startswith('https://'):
                    # Extract domain from URL
                    from urllib.parse import urlparse
                    parsed = urlparse(full_domain)
                    client_domain = f"https://{parsed.netloc}"
                else:
                    # Use domain as-is, add https if needed
                    client_domain = f"https://{full_domain}" if not full_domain.startswith('http') else full_domain
            
            # Create appropriate success message
            if is_free_trial:
                message = f'Successfully started free trial for {package.pkg_name} and initiated deployment'
            else:
                message = f'Successfully created SaaS instance for {package.pkg_name} and generated invoice'
            
            return {
                'success': True,
                'client_id': saas_client.id,
                'client_domain': client_domain,
                'invoice_portal_url': invoice_portal_url,
                'message': message,
                'is_free_trial': is_free_trial
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Failed to create SaaS instance: {str(e)}'
            }

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