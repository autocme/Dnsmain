from odoo import http, _
from odoo.http import request
from odoo.exceptions import ValidationError, AccessError
import hashlib
from datetime import datetime


class BatchPaymentController(http.Controller):

    @http.route('/batch_payment/<string:access_token>', type='http', auth='public', website=True)
    def batch_payment_page(self, access_token, **kwargs):
        """Display batch payment page for customer."""
        try:
            # Find batch payment record by token
            batch_payment = request.env['batch.payment'].sudo().search([
                ('payment_token', '=', access_token),
                ('state', '=', 'link_generated')
            ], limit=1)
            
            if not batch_payment:
                return request.render('j_batch_payment_link.batch_payment_error', {
                    'error_message': _('Invalid or expired payment link.')
                })
            
            # Prepare payment data
            payment_data = {
                'batch_payment': batch_payment,
                'partner': batch_payment.partner_id,
                'invoices': batch_payment.invoice_ids,
                'total_amount': batch_payment.total_amount,
                'currency': batch_payment.currency_id,
                'access_token': access_token,
            }
            
            return request.render('j_batch_payment_link.batch_payment_page', payment_data)
            
        except Exception as e:
            return request.render('j_batch_payment_link.batch_payment_error', {
                'error_message': _('An error occurred while processing your request.')
            })

    @http.route('/batch_payment/<string:access_token>/process', type='http', auth='public', 
                methods=['POST'], website=True, csrf=False)
    def process_batch_payment(self, access_token, **kwargs):
        """Process the batch payment."""
        try:
            # Find batch payment record
            batch_payment = request.env['batch.payment'].sudo().search([
                ('payment_token', '=', access_token),
                ('state', '=', 'link_generated')
            ], limit=1)
            
            if not batch_payment:
                return request.render('j_batch_payment_link.batch_payment_error', {
                    'error_message': _('Invalid or expired payment link.')
                })
            
            # For now, we'll redirect to Odoo's payment form with the correct amount
            # This creates a proper payment transaction through Odoo's payment system
            payment_link_wizard = request.env['payment.link.wizard'].sudo().create({
                'amount': batch_payment.total_amount,
                'currency_id': batch_payment.currency_id.id,
                'partner_id': batch_payment.partner_id.id,
                'description': f'Batch payment for {len(batch_payment.invoice_ids)} invoices',
            })
            
            # Generate the payment link through the wizard
            result = payment_link_wizard.action_generate_payment_link()
            
            if result.get('url'):
                return request.redirect(result['url'])
            else:
                return request.render('j_batch_payment_link.batch_payment_error', {
                    'error_message': _('Unable to process payment at this time.')
                })
                
        except Exception as e:
            return request.render('j_batch_payment_link.batch_payment_error', {
                'error_message': _('An error occurred while processing your payment.')
            })