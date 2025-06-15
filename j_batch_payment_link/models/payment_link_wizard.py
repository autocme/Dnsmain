
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
    
    @api.model
    def default_get(self, fields_list):
        """Override to handle batch payment context"""
        res = super().default_get(fields_list)
        
        # Check if we're in batch payment context
        active_ids = self.env.context.get('active_ids', [])
        if self.env.context.get('active_model') == 'account.move' and len(active_ids) > 1:
            invoices = self.env['account.move'].browse(active_ids)
            res.update({
                'is_batch_payment': True,
                'batch_invoice_ids': [(6, 0, active_ids)],
                'amount': sum(invoices.mapped('amount_residual')),
                'currency_id': invoices[0].currency_id.id,
                'partner_id': invoices[0].partner_id.id,
                'description': f"Batch payment for invoices: {', '.join(invoices.mapped('name'))}",
            })
            
        return res
    
    def _get_additional_create_values(self):
        """Override to set proper values for batch payments"""
        values = super()._get_additional_create_values()
        
        if self.is_batch_payment and self.batch_invoice_ids:
            # For batch payments, link to the first invoice but store batch info
            values.update({
                'res_model': 'account.move',
                'res_id': self.batch_invoice_ids[0].id,
            })
            
        return values
    
    def action_generate_link(self):
        """Override to handle batch payment link generation"""
        if self.is_batch_payment and self.batch_invoice_ids:
            # Verify all invoices are still valid for batch payment
            self._validate_batch_invoices()
            
            # Store batch invoice info in description for payment reconciliation
            invoice_names = ', '.join(self.batch_invoice_ids.mapped('name'))
            invoice_ids_str = ','.join(str(inv_id) for inv_id in self.batch_invoice_ids.ids)
            
            # Update description to include batch info
            self.description = f"Batch payment for invoices: {invoice_names} [BATCH_IDS:{invoice_ids_str}]"
            
            # Ensure amount matches total of all invoices
            total_amount = sum(self.batch_invoice_ids.mapped('amount_residual'))
            if abs(self.amount - total_amount) > 0.01:  # Allow for rounding differences
                self.amount = total_amount
            
        return super().action_generate_link()
    
    def _validate_batch_invoices(self):
        """Validate that batch invoices are still eligible for payment"""
        if not self.batch_invoice_ids:
            raise UserError(_('No invoices selected for batch payment.'))
            
        # Check if all invoices are still posted and have amounts due
        non_posted = self.batch_invoice_ids.filtered(lambda inv: inv.state != 'posted')
        if non_posted:
            raise UserError(_(
                'All invoices must be posted. Non-posted invoices: %s'
            ) % ', '.join(non_posted.mapped('name')))
            
        paid_invoices = self.batch_invoice_ids.filtered(lambda inv: inv.amount_residual <= 0)
        if paid_invoices:
            raise UserError(_(
                'All invoices must have outstanding amounts. Already paid invoices: %s'
            ) % ', '.join(paid_invoices.mapped('name')))


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'
    
    def _reconcile_after_done(self):
        """Override to handle batch payment reconciliation"""
        # Check if this is a batch payment
        if self.reference and '[BATCH_IDS:' in self.reference:
            self._reconcile_batch_payment()
        else:
            return super()._reconcile_after_done()
    
    def _reconcile_batch_payment(self):
        """Handle reconciliation for batch payments"""
        # Extract invoice IDs from reference
        start_marker = '[BATCH_IDS:'
        end_marker = ']'
        start_idx = self.reference.find(start_marker) + len(start_marker)
        end_idx = self.reference.find(end_marker, start_idx)
        
        if start_idx > len(start_marker) - 1 and end_idx > start_idx:
            invoice_ids_str = self.reference[start_idx:end_idx]
            try:
                invoice_ids = [int(x.strip()) for x in invoice_ids_str.split(',') if x.strip()]
                invoices = self.env['account.move'].browse(invoice_ids)
                
                if invoices and self.payment_id:
                    # Allocate payment across invoices
                    self._allocate_payment_to_invoices(invoices)
                    
            except (ValueError, TypeError):
                # Fallback to standard reconciliation
                super()._reconcile_after_done()
    
    def _allocate_payment_to_invoices(self, invoices):
        """Allocate payment amount across multiple invoices"""
        if not self.payment_id or not invoices:
            return
            
        payment = self.payment_id
        remaining_amount = payment.amount
        
        # Create payment allocations for each invoice
        for invoice in invoices:
            if remaining_amount <= 0:
                break
                
            # Calculate allocation for this invoice
            invoice_amount = invoice.amount_residual
            allocation = min(invoice_amount, remaining_amount)
            
            if allocation > 0:
                # Create payment line for this invoice
                payment_vals = {
                    'account_id': invoice.line_ids.filtered(lambda l: l.account_id.account_type in ('asset_receivable', 'liability_payable'))[0].account_id.id,
                    'partner_id': invoice.partner_id.id,
                    'move_id': payment.move_id.id,
                    'name': f'Payment allocation for {invoice.name}',
                    'debit': 0.0,
                    'credit': allocation,
                    'amount_currency': -allocation,
                    'currency_id': payment.currency_id.id,
                }
                
                payment_line = self.env['account.move.line'].create(payment_vals)
                
                # Reconcile with invoice
                invoice_line = invoice.line_ids.filtered(lambda l: l.account_id.account_type in ('asset_receivable', 'liability_payable'))
                if invoice_line and payment_line:
                    (invoice_line + payment_line).reconcile()
                
                remaining_amount -= allocation
