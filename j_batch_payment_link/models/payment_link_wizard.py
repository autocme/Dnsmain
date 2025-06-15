
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class PaymentLinkWizard(models.TransientModel):
    _inherit = 'payment.link.wizard'
    
    batch_invoice_ids = fields.Many2many(
        'account.move', 
        string='Batch Invoices',
        help='Invoices included in this batch payment'
    )
    is_batch_payment = fields.Boolean('Is Batch Payment', default=False)
    
    def _get_payment_values(self):
        """Override to handle batch payment values"""
        values = super()._get_payment_values()
        
        if self.batch_invoice_ids:
            # For batch payments, we need to ensure proper invoice linking
            values.update({
                'invoice_ids': [(6, 0, self.batch_invoice_ids.ids)],
                'communication': self.description or ', '.join(self.batch_invoice_ids.mapped('name')),
            })
            
        return values
    
    @api.model
    def _process_payment_allocation(self, payment, invoice_ids):
        """Allocate payment across multiple invoices"""
        if not invoice_ids:
            return
            
        invoices = self.env['account.move'].browse(invoice_ids)
        total_payment = payment.amount
        
        for invoice in invoices:
            if total_payment <= 0:
                break
                
            # Calculate allocation for this invoice
            allocation = min(invoice.amount_residual, total_payment)
            
            if allocation > 0:
                # Create payment allocation record
                payment.write({
                    'reconciled_invoice_ids': [(4, invoice.id)]
                })
                total_payment -= allocation
