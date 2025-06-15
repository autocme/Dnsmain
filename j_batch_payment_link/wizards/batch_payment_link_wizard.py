from odoo import models, fields, api, _
from odoo.exceptions import UserError
import hashlib
from datetime import datetime


class BatchPaymentLinkWizard(models.TransientModel):
    """Simple wizard to generate payment links for batch invoices."""
    _name = 'batch.payment.link.wizard'
    _description = 'Batch Payment Link Generator'

    # Invoice Information
    invoice_ids = fields.Many2many(
        'account.move',
        string='Invoices',
        readonly=True
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        readonly=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        readonly=True
    )
    
    # Amount Information
    total_amount = fields.Monetary(
        string='Total Amount',
        currency_field='currency_id',
        readonly=True
    )
    invoice_count = fields.Integer(
        string='Number of Invoices',
        readonly=True
    )
    
    # Payment Link Information
    payment_link = fields.Char(
        string='Payment Link',
        readonly=True
    )
    description = fields.Text(
        string='Description',
        default='Batch payment for multiple invoices'
    )
    
    @api.model
    def default_get(self, fields_list):
        """Set default values from context."""
        result = super().default_get(fields_list)
        
        # Get invoice IDs from context
        invoice_ids = self.env.context.get('active_ids', [])
        if invoice_ids:
            invoices = self.env['account.move'].browse(invoice_ids)
            
            result.update({
                'invoice_ids': [(6, 0, invoice_ids)],
                'partner_id': invoices[0].partner_id.id if invoices else False,
                'currency_id': invoices[0].currency_id.id if invoices else False,
                'total_amount': sum(invoices.mapped('amount_residual')),
                'invoice_count': len(invoices),
                'description': f'Batch payment for {len(invoices)} invoices'
            })
        
        return result
    
    def action_generate_payment_link(self):
        """Generate payment link for batch payment."""
        self.ensure_one()
        
        # Generate unique token for the payment link
        token_data = f"batch-{self.partner_id.id}-{self.total_amount}-{datetime.now().isoformat()}"
        access_token = hashlib.sha256(token_data.encode()).hexdigest()
        
        # Get base URL
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        
        # Generate payment link using Odoo's payment format
        # Use the first invoice as reference but with total amount
        first_invoice = self.invoice_ids[0] if self.invoice_ids else False
        if not first_invoice:
            raise UserError(_('No invoices found for batch payment.'))
        
        # Create payment link
        self.payment_link = f"{base_url}/payment/pay?amount={self.total_amount}&access_token={access_token}&invoice_id={first_invoice.id}&batch_mode=1"
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'batch.payment.link.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {'show_payment_link': True}
        }
    
    def action_copy_link(self):
        """Copy payment link to clipboard (client-side action)."""
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Payment Link'),
                'message': _('Payment link: %s') % self.payment_link,
                'type': 'info',
                'sticky': True,
            }
        }