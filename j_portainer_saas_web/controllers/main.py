#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import http, fields
from odoo.http import request
import json
import time
from datetime import timedelta
from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.controllers.post_processing import PaymentPostProcessing
import logging

_logger = logging.getLogger(__name__)


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

            import logging
            _logger = logging.getLogger(__name__)

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

                    # Free trial deployment completed - JavaScript will handle direct redirect

                except Exception as e:
                    _logger.warning(f"Failed to deploy free trial client {saas_client.id}: {e}")

            # Get direct payment link for paid packages and flag the first invoice
            payment_link = None
            if not is_free_trial and saas_client.sc_subscription_id:
                try:
                    # Get the latest invoice from the subscription
                    invoices = saas_client.sc_subscription_id.invoice_ids
                    if invoices:
                        latest_invoice = invoices[-1]  # Get the most recent invoice

                        # Flag this as the first SaaS invoice for payment monitoring
                        latest_invoice.sudo().write({'is_saas_first_invoice': True})

                        # Generate direct payment link like the payment wizard does
                        try:
                            access_token = payment_utils.generate_access_token(
                                latest_invoice.partner_id.id, latest_invoice.amount_total, latest_invoice.currency_id.id
                            )
                            base_url = request.httprequest.url_root.rstrip('/')
                            payment_link = f"{base_url}/payment/pay?amount={latest_invoice.amount_total}&access_token={access_token}&invoice_id={latest_invoice.id}"
                            _logger.info(f"Generated payment link for invoice {latest_invoice.id} for paid client {saas_client.id}")
                        except Exception as token_error:
                            _logger.warning(f"Failed to generate payment link for client {saas_client.id}: {token_error}")
                            payment_link = f"/my/invoices/{latest_invoice.id}"  # Fallback to portal URL

                        _logger.info(f"Found and flagged invoice {latest_invoice.id} as first SaaS invoice for paid client {saas_client.id}")
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
                'payment_link': payment_link,
                'message': message,
                'is_free_trial': is_free_trial
            }

        except Exception as e:
            return {
                'success': False,
                'error': f'Failed to create SaaS instance: {str(e)}'
            }

    @http.route('/saas/client/invoice_info', type='http', auth='user', methods=['GET'], csrf=False)
    def get_client_invoice_info(self, client_id, **kwargs):
        """
        Get invoice information for a SaaS client

        Args:
            client_id: SaaS client ID

        Returns:
            JSON with invoice_id and access_token
        """
        try:
            import logging
            _logger = logging.getLogger(__name__)

            client_id_int = int(client_id)
            client = request.env['saas.client'].sudo().browse(client_id_int)

            if not client.exists():
                return request.make_response(
                    json.dumps({'success': False, 'error': 'Client not found'}),
                    headers=[('Content-Type', 'application/json')]
                )

            # Check if client belongs to current user
            if client.sc_partner_id.id != request.env.user.partner_id.id:
                return request.make_response(
                    json.dumps({'success': False, 'error': 'Access denied'}),
                    headers=[('Content-Type', 'application/json')]
                )

            # Get the subscription and invoice
            subscription = client.sc_subscription_id
            if not subscription:
                return request.make_response(
                    json.dumps({'success': False, 'error': 'No subscription found'}),
                    headers=[('Content-Type', 'application/json')]
                )

            # Get unpaid invoices from subscription (including draft invoices that need payment)
            unpaid_invoices = subscription.invoice_ids.filtered(
                lambda inv: (
                    # Posted invoices that are unpaid or partially paid
                    (inv.state == 'posted' and inv.payment_state in ['not_paid', 'partial']) or
                    # Draft invoices with amount > 0 (need to be paid)
                    (inv.state == 'draft' and inv.amount_total > 0)
                )
            )

            if not unpaid_invoices:
                # Debug: show what invoices exist for this subscription
                all_invoices = subscription.invoice_ids
                invoice_debug = [f"ID:{inv.id} State:{inv.state} Payment:{getattr(inv, 'payment_state', 'N/A')} Amount:{inv.amount_total}" for inv in all_invoices]
                return request.make_response(
                    json.dumps({'success': False, 'error': f'No unpaid invoice found. Debug - All invoices: {invoice_debug}'}),
                    headers=[('Content-Type', 'application/json')]
                )

            # Get the first unpaid invoice
            invoice = unpaid_invoices[0]

            # Generate access token for invoice
            access_token = payment_utils.generate_access_token(
                invoice.partner_id.id, invoice.amount_total, invoice.currency_id.id
            )

            _logger.info(f"Retrieved invoice info for client {client_id}: invoice_id={invoice.id}")

            return request.make_response(
                json.dumps({
                    'success': True,
                    'invoice_id': invoice.id,
                    'access_token': access_token,
                    'amount': float(invoice.amount_residual),
                    'currency': invoice.currency_id.name
                }),
                headers=[('Content-Type', 'application/json')]
            )

        except Exception as e:
            _logger.error(f"Error getting invoice info for client {client_id}: {str(e)}")
            return request.make_response(
                json.dumps({'success': False, 'error': str(e)}),
                headers=[('Content-Type', 'application/json')]
            )

    # Note: Payment status checking removed - now handled automatically by account.move payment detection

    @http.route('/saas/invoice/open_payment_wizard', type='json', auth='user', methods=['POST'])
    def open_invoice_payment_wizard(self, invoice_id, client_id=None, **kwargs):
        """
        Open Odoo's native invoice payment wizard

        This method returns an action to open the payment wizard modal
        using Odoo's built-in payment registration system
        """
        try:
            import logging
            _logger = logging.getLogger(__name__)

            _logger.info(f"Opening payment wizard for invoice {invoice_id}, client {client_id}")

            invoice_id_int = int(invoice_id)
            invoice = request.env['account.move'].sudo().browse(invoice_id_int)

            if not invoice.exists():
                return {'success': False, 'error': 'Invoice not found'}

            # Check if user has access to this invoice
            if invoice.partner_id.id != request.env.user.partner_id.id:
                return {'success': False, 'error': 'Access denied'}

            # Create payment wizard action using Odoo's standard payment registration
            action = {
                'name': 'Pay with',
                'type': 'ir.actions.act_window',
                'res_model': 'account.payment.register',
                'view_mode': 'form',
                'views': [(False, 'form')],
                'target': 'new',
                'context': {
                    'active_model': 'account.move',
                    'active_ids': [invoice_id_int],
                    'active_id': invoice_id_int,
                    'default_invoice_ids': [(6, 0, [invoice_id_int])],
                    'saas_client_id': client_id,
                    'saas_mode': True,
                },
                'flags': {
                    'mode': 'edit',
                }
            }

            _logger.info(f"Payment wizard action created: {action}")

            return {
                'success': True,
                'action': action,
                'invoice_amount': invoice.amount_residual,
                'invoice_currency': invoice.currency_id.symbol,
                'invoice_name': invoice.name
            }

        except Exception as e:
            _logger.error(f"Error opening payment wizard for invoice {invoice_id}: {str(e)}")
            return {'success': False, 'error': str(e)}

    @http.route(['/saas/invoice/payment_wizard', '/saas/test/wizard'], type='http', auth='user', methods=['GET', 'POST'], csrf=False)
    def get_invoice_payment_wizard(self, **kwargs):
        """
        Get invoice payment wizard HTML for a SaaS client

        Args:
            client_id (int): SaaS client ID

        Returns:
            HTML fragment for invoice payment wizard
        """
        try:
            import logging
            _logger = logging.getLogger(__name__)

            # Check if this is the test route
            if request.httprequest.path == '/saas/test/wizard':
                return request.make_response('Controller is working - test route OK', headers=[('Content-Type', 'text/plain')])

            # Get client_id from parameters
            client_id = kwargs.get('client_id')
            _logger.info(f"Payment wizard request: client_id={client_id}, kwargs={kwargs}")

            # Check if client_id parameter is provided
            if client_id is None:
                _logger.error("No client_id parameter provided")
                return request.make_response('Missing client_id parameter', status=400)

            # Get the SaaS client
            try:
                client_id_int = int(client_id)
                _logger.info(f"Client ID converted to int: {client_id_int}")
            except (ValueError, TypeError) as e:
                _logger.error(f"Invalid client_id format: {client_id}, error: {e}")
                return request.make_response(f'Invalid client ID format: {client_id}', status=400)

            client = request.env['saas.client'].sudo().browse(client_id_int)
            if not client.exists():
                return request.make_response('Client not found', status=404)

            # Check if client belongs to current user
            if client.sc_partner_id.id != request.env.user.partner_id.id:
                return request.make_response('Access denied', status=403)

            # Get the subscription and its invoices
            if not client.sc_subscription_id:
                return request.make_response('No subscription found for this client', status=404)

            subscription = client.sc_subscription_id
            # Get unpaid invoices from subscription (including draft invoices that need payment)
            invoices = subscription.invoice_ids.filtered(
                lambda inv: (
                    # Posted invoices that are unpaid or partially paid
                    (inv.state == 'posted' and inv.payment_state in ['not_paid', 'partial']) or
                    # Draft invoices with amount > 0 (need to be paid)
                    (inv.state == 'draft' and inv.amount_total > 0)
                )
            )

            if not invoices:
                # Debug: show what invoices exist for this subscription
                all_invoices = subscription.invoice_ids
                invoice_debug = [f"ID:{inv.id} State:{inv.state} Payment:{getattr(inv, 'payment_state', 'N/A')} Amount:{inv.amount_total}" for inv in all_invoices]
                return request.make_response(f'No unpaid invoices found. Debug - All invoices: {invoice_debug}', status=404)

            # Get the latest unpaid invoice
            invoice = invoices[-1]

            _logger.info(f"Getting payment wizard for client {client.id}, invoice {invoice.id}")

            # Get payment providers
            try:
                providers = request.env['payment.provider'].sudo().search([('state', '=', 'enabled')])
                if not providers:
                    # Try to get any available providers if none are enabled
                    providers = request.env['payment.provider'].sudo().search([])
                    if not providers:
                        return request.make_response('No payment providers available', status=500)
            except Exception as e:
                _logger.error(f"Error accessing payment providers: {str(e)}")
                return request.make_response('Payment system not available', status=500)

            # Get additional payment data
            try:
                payment_methods = request.env['payment.method'].sudo().search([])
                tokens = request.env['payment.token'].sudo().search([('partner_id', '=', request.env.user.partner_id.id)])
            except Exception as e:
                _logger.warning(f"Error accessing payment methods/tokens: {str(e)}")
                payment_methods = request.env['payment.method'].sudo().browse()
                tokens = request.env['payment.token'].sudo().browse()

            # Generate access token
            access_token = payment_utils.generate_access_token(
                invoice.partner_id.id, invoice.amount_total, invoice.currency_id.id
            )

            # Prepare payment wizard data
            payment_data = {
                'invoice': invoice,
                'client': client,
                'providers_sudo': providers,
                'payment_methods_sudo': payment_methods,
                'tokens_sudo': tokens,
                'amount': invoice.amount_residual,
                'currency': invoice.currency_id,
                'partner_id': request.env.user.partner_id.id,
                'reference': f"Invoice {invoice.name}",
                'reference_prefix': 'INV',
                'transaction_route': '/payment/transaction',
                'landing_route': f'/saas/payment/invoice_success/{client.id}',
                'access_token': access_token,
                'mode': 'payment',
                'allow_token_selection': True,
                'allow_token_deletion': False,
                'default_token_id': False,
            }

            _logger.info(f"Payment wizard data prepared: providers={len(providers)}, amount={invoice.amount_residual}, currency={invoice.currency_id.name}, access_token={'***' if access_token else 'None'}")

            # Verify template exists before rendering
            try:
                template = request.env.ref('j_portainer_saas_web.invoice_payment_wizard')
                _logger.info(f"Template found: {template}")
            except Exception as template_err:
                _logger.error(f"Template not found: {template_err}")
                return request.make_response(f'Template error: {str(template_err)}', status=500)

            # Render the payment wizard template
            _logger.info("Attempting to render payment wizard template...")
            try:
                result = request.render('j_portainer_saas_web.invoice_payment_wizard', payment_data)
                _logger.info("Payment wizard template rendered successfully")
                return result
            except Exception as render_err:
                _logger.error(f"Template rendering failed: {render_err}")
                raise render_err

        except Exception as e:
            _logger.error(f"Error getting payment wizard for client {client_id}: {str(e)}")

            # Return a user-friendly fallback HTML with error message
            fallback_html = f"""
            <div class="saas_payment_wizard_container">
                <div class="alert alert-danger">
                    <h5><i class="fa fa-exclamation-triangle"></i> Payment System Error</h5>
                    <p>Unable to load the payment wizard at this time.</p>
                    <p><strong>Error:</strong> {str(e)}</p>
                    <div class="mt-3">
                        <button type="button" class="btn btn-primary" onclick="location.reload();">
                            <i class="fa fa-refresh"></i> Retry
                        </button>
                        <a href="/my/invoices" class="btn btn-secondary ml-2">
                            <i class="fa fa-external-link"></i> View Invoices
                        </a>
                    </div>
                </div>
            </div>
            """
            return request.make_response(fallback_html, headers=[('Content-Type', 'text/html')])

    @http.route(['/saas/payment/success', '/saas/payment/invoice_success/<int:client_id>'], type='http', auth='user', methods=['GET'], csrf=False)
    def invoice_payment_success(self, client_id=None, **kwargs):
        """
        Handle successful invoice payment and redirect to client instance

        Args:
            client_id (int): SaaS client ID

        Returns:
            Redirect to client instance or success page
        """
        try:
            import logging
            _logger = logging.getLogger(__name__)

            client = request.env['saas.client'].sudo().browse(client_id)
            if not client.exists():
                return request.redirect('/web')

            # Check if client belongs to current user
            if client.sc_partner_id.id != request.env.user.partner_id.id:
                return request.redirect('/web')

            _logger.info(f"Payment successful for client {client.id}, checking deployment status...")

            # Clear the first invoice flag to prevent duplicate redirects
            invoice = transaction.invoice_ids[0]
            invoice.sudo().write({'is_saas_first_invoice': False})

            # Get the client domain for redirect first
            client_domain = None
            if saas_client.sc_full_domain:
                full_domain = saas_client.sc_full_domain.strip()
                if full_domain:
                    if full_domain.startswith('http://') or full_domain.startswith('https://'):
                        client_domain = full_domain
                    else:
                        client_domain = f"https://{full_domain}"

            if not client_domain:
                _logger.warning('No valid client domain found for SaaS client %s, falling back to default', saas_client.id)
                return super().display_status(**kwargs)

            # Deploy the client if not already deployed or running
            deployment_needed = saas_client.sc_status in ['draft', 'ready']

            if deployment_needed:
                try:
                    _logger.info('Deploying SaaS client %s after successful payment', saas_client.id)
                    saas_client.action_deploy_client()
                    _logger.info('Client %s deployment initiated successfully', saas_client.id)
                except Exception as e:
                    _logger.warning('Failed to deploy client %s after payment: %s', saas_client.id, e)
                    # Continue with redirect even if deployment fails
            else:
                _logger.info('Client %s already deployed (status: %s), proceeding with redirect', saas_client.id, saas_client.sc_status)

            _logger.info('Redirecting user to SaaS client instance: %s', client_domain)

            # Show the same loading screen as free trial before redirecting
            redirect_data = {
                'client': saas_client,
                'client_domain': client_domain,
                'redirect_delay': 5,  # 5 seconds to allow for deployment completion
                'package_name': saas_client.sc_package_id.pkg_name,
                'is_paid_package': True,
                'deployment_initiated': deployment_needed
            }

            return request.render('j_portainer_saas_web.payment_success_redirect', redirect_data)

        except Exception as e:
            _logger.error(f"Error in invoice payment success for client {client_id}: {str(e)}")
            return request.redirect('/web')



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

    @http.route('/saas/client/open_payment_wizard', type='json', auth='user', methods=['POST'], csrf=False)
    def open_payment_wizard(self, client_id, **kwargs):
        """
        Open Odoo's standard payment wizard for SaaS client invoice

        Args:
            client_id (int): SaaS client ID

        Returns:
            JSON response with payment wizard action or portal URL
        """
        print(f"=== Starting open_payment_wizard for client_id: {client_id} ===")

        try:
            print(f"Step 1: Checking models availability...")
            # Check if models exist
            if 'saas.client' not in request.env:
                print("ERROR: SaaS client model not found")
                return {
                    'success': False,
                    'error': 'SaaS client model not found'
                }

            print(f"Step 2: Getting SaaS client with ID: {client_id}")
            # Get the SaaS client
            client = request.env['saas.client'].sudo().browse(int(client_id))
            if not client.exists():
                print(f"ERROR: SaaS client {client_id} not found")
                return {
                    'success': False,
                    'error': 'SaaS client not found'
                }

            print(f"Step 3: Found client {client.id}, checking subscription...")

            # Get the subscription and its invoices
            if not client.sc_subscription_id:
                return {
                    'success': False,
                    'error': 'No subscription found for this client'
                }

            subscription = client.sc_subscription_id
            # Get unpaid invoices from subscription (including draft invoices that need payment)
            unpaid_invoices = subscription.invoice_ids.filtered(
                lambda inv: (
                    # Posted invoices that are unpaid or partially paid
                    (inv.state == 'posted' and inv.payment_state in ['not_paid', 'partial']) or
                    # Draft invoices with amount > 0 (need to be paid)
                    (inv.state == 'draft' and inv.amount_total > 0)
                )
            )

            if not unpaid_invoices:
                # Debug: show what invoices exist for this subscription
                all_invoices = subscription.invoice_ids
                invoice_debug = [f"ID:{inv.id} State:{inv.state} Payment:{getattr(inv, 'payment_state', 'N/A')} Amount:{inv.amount_total}" for inv in all_invoices]
                return {
                    'success': False,
                    'error': f'No unpaid invoices found for this subscription. Debug - All invoices: {invoice_debug}'
                }

            # Get the first unpaid invoice
            invoice = unpaid_invoices[0]

            # Generate direct payment link like "Generate a payment link" server action
            try:
                print(f"Generating direct payment link for invoice {invoice.id}, amount: {invoice.amount_total}")

                # Ensure invoice has required fields
                if not invoice.amount_total or invoice.amount_total <= 0:
                    return {
                        'success': False,
                        'error': f'Invalid invoice amount: {invoice.amount_total}'
                    }

                # Generate access token for the invoice using the same method as portal
                try:
                    access_token = payment_utils.generate_access_token(
                    invoice.partner_id.id, invoice.amount_total, invoice.currency_id.id
                    )
                    print(f"Access token generated: {access_token[:10]}...{access_token[-10:]} (length: {len(access_token)})")
                except Exception as token_error:
                    print(f"Error generating access token: {token_error}")
                    return {
                        'success': False,
                        'error': f'Unable to generate access token: {str(token_error)}'
                    }

                # Generate standard payment link without custom redirect parameter
                # The redirect will be handled by the payment completion monitoring in account_move.py
                base_url = request.httprequest.url_root.rstrip('/')
                payment_link = f"{base_url}/payment/pay?amount={invoice.amount_total}&access_token={access_token}&invoice_id={invoice.id}"

                print(f"Generated payment link: {payment_link}")
                print(f"Invoice details - ID: {invoice.id}, Amount: {invoice.amount_total}, Currency: {invoice.currency_id.name}, Partner: {invoice.partner_id.name}")

                return {
                    'success': True,
                    'payment_link': payment_link,
                    'invoice_id': invoice.id,
                    'invoice_name': invoice.name,
                    'invoice_amount': float(invoice.amount_total),
                    'invoice_currency': invoice.currency_id.name,
                    'access_token': access_token[:10] + '...' + access_token[-10:],  # Partial token for debugging
                    'message': 'Payment link generated successfully'
                }

            except Exception as e:
                print(f"Payment link generation failed: {type(e).__name__}: {str(e)}")
                import traceback
                traceback.print_exc()

                return {
                    'success': False,
                    'error': f'Unable to generate payment link: {str(e)}'
                }

        except Exception as e:
            print(f"=== MAIN EXCEPTION in open_payment_wizard ===")
            print(f"Exception type: {type(e).__name__}")
            print(f"Exception message: {str(e)}")
            import traceback
            traceback.print_exc()
            print(f"=== END EXCEPTION ===")
            return {
                'success': False,
                'error': f'Server error: {str(e)}'
            }

    def _get_support_phone_message(self):
        """
        Get support phone number from settings and format contact message
        
        Returns:
            str: Formatted support contact message
        """
        try:
            support_phone = request.env['ir.config_parameter'].sudo().get_param('j_portainer_saas_web.support_phone', '')
            if support_phone:
                return f'System creation failed. Please contact support at {support_phone} for assistance.'
            else:
                return 'System creation failed. Please contact support for assistance.'
        except Exception:
            return 'System creation failed. Please contact support for assistance.'

    @http.route('/saas/support/phone', type='json', auth='public', methods=['GET', 'POST'])
    def get_support_phone_number(self):
        """
        Get support phone number from settings for frontend error messages
        
        Returns:
            JSON response with support phone number or default message
        """
        try:
            support_phone = request.env['ir.config_parameter'].sudo().get_param('j_portainer_saas_web.support_phone', '')
            if support_phone:
                return {
                    'success': True,
                    'support_phone': support_phone,
                    'error_message': f'System creation failed. Please contact support at {support_phone} for assistance.'
                }
            else:
                return {
                    'success': True,
                    'support_phone': '',
                    'error_message': 'System creation failed. Please contact support for assistance.'
                }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'error_message': 'System creation failed. Please contact support for assistance.'
            }

    @http.route('/saas/client/deployment_status/<int:client_id>', type='json', auth='user', methods=['POST'])
    def check_deployment_status(self, client_id):
        """
        Check the deployment status of a SaaS client by monitoring job queue
        
        Args:
            client_id (int): ID of the SaaS client
            
        Returns:
            dict: Status information including job state and deployment status
        """
        try:
            # Find the SaaS client
            client = request.env['saas.client'].browse(client_id)
            if not client.exists():
                return {
                    'success': False,
                    'error': 'Client not found',
                    'status': 'error'
                }
            
            # Check if client is already deployed/running
            if client.sc_status == 'running':
                return {
                    'success': True,
                    'status': 'completed',
                    'deployment_complete': True,
                    'client_domain': client.sc_full_domain,
                    'message': 'Deployment completed successfully'
                }
            
            # Check for job queue status
            # Look for deployment jobs for this client
            jobs = request.env['queue.job'].sudo().search([
                ('model_name', '=', 'saas.client'),
                ('record_ids', 'like', f'[{client_id}]'),
                ('method_name', '=', 'action_deploy')
            ], order='date_created desc', limit=1)
            
            if jobs:
                job = jobs[0]
                _logger.info(f'Found deployment job {job.id} with state: "{job.state}" (type: {type(job.state)})')
                _logger.info(f'Job details: id={job.id}, uuid={job.uuid}, state="{job.state}", date_created={job.date_created}, date_started={job.date_started}, date_done={job.date_done}')
                
                if job.state == 'done':
                    # Job completed successfully, update client status if needed
                    if client.sc_status != 'running':
                        client.sudo().write({'sc_status': 'running'})
                    
                    return {
                        'success': True,
                        'status': 'completed',
                        'deployment_complete': True,
                        'client_domain': client.sc_full_domain,
                        'message': 'System ready! Redirecting to your instance...'
                    }
                elif job.state == 'failed':
                    return {
                        'success': True,
                        'status': 'failed',
                        'deployment_complete': False,
                        'error_message': 'System creation failed. Please contact support for assistance.',
                        'message': 'System creation encountered an error'
                    }
                elif job.state == 'cancelled':
                    return {
                        'success': True,
                        'status': 'cancel',
                        'deployment_complete': False,
                        'error_message': 'System creation was cancelled. Please contact support for assistance.',
                        'message': 'System creation was cancelled'
                    }
                else:
                    # Job is still pending/started or unknown state
                    _logger.warning(f'Unexpected job state "{job.state}" for job {job.id}, treating as deploying')
                    return {
                        'success': True,
                        'status': 'deploying',
                        'deployment_complete': False,
                        'message': 'Creating your system...'
                    }
            else:
                # No job found, deployment might not have started yet
                return {
                    'success': True,
                    'status': 'pending',
                    'deployment_complete': False,
                    'message': 'System creation starting...'
                }
                
        except Exception as e:
            _logger.error(f'Error checking deployment status for client {client_id}: {str(e)}')
            return {
                'success': False,
                'error': f'Error checking deployment status: {str(e)}',
                'status': 'error'
            }


class CustomPaymentPortal(PaymentPostProcessing):
    """Override payment post-processing to handle SaaS client redirects"""

    _logger = logging.getLogger(__name__)

    @http.route('/payment/status', type='http', auth="public", website=True, sitemap=False)
    def display_status(self, **kwargs):
        """Override payment status to redirect SaaS clients to their instance after successful payment"""
        _logger.info('CustomPaymentPortal: display_status called with kwargs: %s', kwargs)

        try:
            # First, try to get transaction from session or various parameter sources
            tx_reference = None
            transaction = None

            # Method 1: Check session for transaction
            if hasattr(request, 'session') and request.session.get('__payment_tx_id__'):
                tx_id = request.session.get('__payment_tx_id__')
                transaction = request.env['payment.transaction'].sudo().browse(int(tx_id))
                if transaction.exists():
                    tx_reference = transaction.reference
                    _logger.info('Found transaction %s from session', tx_reference)

            # Method 2: Check various parameter formats
            if not tx_reference:
                tx_reference = (kwargs.get('reference') or 
                              kwargs.get('tx_reference') or 
                              kwargs.get('transaction_id') or
                              kwargs.get('tx_id'))

            # Method 3: Check for recent completed transactions for current user
            if not tx_reference and request.env.user and not request.env.user._is_public():
                recent_transactions = request.env['payment.transaction'].sudo().search([
                    ('partner_id', '=', request.env.user.partner_id.id),
                    ('state', '=', 'done'),
                    ('create_date', '>=', fields.Datetime.now() - timedelta(minutes=10))
                ], order='create_date desc', limit=5)

                # Look for SaaS-related transactions
                for tx in recent_transactions:
                    if tx.invoice_ids.filtered('is_saas_first_invoice'):
                        transaction = tx
                        tx_reference = tx.reference
                        _logger.info('Found recent SaaS transaction %s for user', tx_reference)
                        break

            if not tx_reference and not transaction:
                _logger.info('No transaction reference found, falling back to default behavior')
                return super().display_status(**kwargs)

            # Find the payment transaction if we only have reference
            if not transaction and tx_reference:
                transaction = request.env['payment.transaction'].sudo().search([
                    ('reference', '=', tx_reference),
                    ('state', '=', 'done')
                ], limit=1)

            if not transaction:
                _logger.info('No successful transaction found for reference %s', tx_reference)
                return super().display_status(**kwargs)

            # Check if this transaction is related to SaaS package purchase
            # First, check if any invoice has the SaaS first invoice flag
            saas_invoices = transaction.invoice_ids.filtered('is_saas_first_invoice')
            if not saas_invoices:
                _logger.info('No SaaS invoices found for transaction %s - not a SaaS package purchase', tx_reference)
                return super().display_status(**kwargs)

            # Get the first SaaS invoice
            invoice = saas_invoices[0]

            # Verify this invoice is actually linked to a SaaS subscription
            if not invoice.subscription_id:
                _logger.info('Invoice %s has SaaS flag but no subscription - falling back to default', invoice.id)
                return super().display_status(**kwargs)

            # Find the SaaS client associated with this subscription
            saas_client = request.env['saas.client'].sudo().search([
                ('sc_subscription_id', '=', invoice.subscription_id.id)
            ], limit=1)

            if not saas_client:
                _logger.warning('No SaaS client found for subscription %s - falling back to default', invoice.subscription_id.id)
                return super().display_status(**kwargs)

            # Additional validation: ensure the SaaS client has a valid package
            if not saas_client.sc_package_id:
                _logger.warning('SaaS client %s has no package - falling back to default', saas_client.id)
                return super().display_status(**kwargs)

            _logger.info('Found SaaS client %s for invoice %s', saas_client.id, invoice.id)

            # Clear the first invoice flag to prevent duplicate redirects
            invoice.sudo().write({'is_saas_first_invoice': False})

            # Get the client domain for redirect first
            client_domain = None
            if saas_client.sc_full_domain:
                full_domain = saas_client.sc_full_domain.strip()
                if full_domain:
                    if full_domain.startswith('http://') or full_domain.startswith('https://'):
                        client_domain = full_domain
                    else:
                        client_domain = f"https://{full_domain}"

            if not client_domain:
                _logger.warning('No valid client domain found for SaaS client %s, falling back to default', saas_client.id)
                return super().display_status(**kwargs)

            # Deploy the client if not already deployed or running
            deployment_needed = saas_client.sc_status in ['draft', 'ready']

            if deployment_needed:
                try:
                    _logger.info('Deploying SaaS client %s after successful payment', saas_client.id)
                    saas_client.action_deploy_client()
                    _logger.info('Client %s deployment initiated successfully', saas_client.id)
                except Exception as e:
                    _logger.warning('Failed to deploy client %s after payment: %s', saas_client.id, e)
                    # Continue with redirect even if deployment fails
            else:
                _logger.info('Client %s already deployed (status: %s), proceeding with redirect', saas_client.id, saas_client.sc_status)

            _logger.info('Redirecting user to SaaS client instance: %s', client_domain)

            # Show the same loading screen as free trial before redirecting
            redirect_data = {
                'client': saas_client,
                'client_domain': client_domain,
                'redirect_delay': 5,  # 5 seconds to allow for deployment completion
                'package_name': saas_client.sc_package_id.pkg_name,
                'is_paid_package': True,
                'deployment_initiated': deployment_needed
            }

            return request.render('j_portainer_saas_web.payment_success_redirect', redirect_data)

        except Exception as e:
            _logger.exception('Error in CustomPaymentPortal: %s', e)
            return super().display_status(**kwargs)