from odoo import models, api, _


class AccountPayment(models.Model):
    _inherit = 'account.payment'
    
    @api.model
    def create(self, vals):
        """Override create to handle batch payment reconciliation."""
        payment = super().create(vals)
        
        # Check if this is a batch payment by looking at the description
        if payment.ref and '[BATCH_IDS:' in payment.ref:
            self._process_batch_payment_reconciliation(payment)
        
        return payment
    
    def _process_batch_payment_reconciliation(self, payment):
        """Process reconciliation for batch payments across multiple invoices."""
        try:
            # Extract invoice IDs from payment reference
            ref = payment.ref or ''
            start_marker = '[BATCH_IDS:'
            end_marker = ']'
            start_idx = ref.find(start_marker)
            end_idx = ref.find(end_marker, start_idx)
            
            if start_idx == -1 or end_idx == -1:
                return
            
            # Get invoice IDs
            start_idx += len(start_marker)
            invoice_ids_str = ref[start_idx:end_idx]
            invoice_ids = [int(x.strip()) for x in invoice_ids_str.split(',') if x.strip().isdigit()]
            
            if not invoice_ids:
                return
                
            # Get the invoices
            invoices = self.env['account.move'].browse(invoice_ids).exists()
            if not invoices:
                return
            
            # Only process if payment is for the same partner
            if invoices.mapped('partner_id') != [payment.partner_id]:
                return
            
            # Get outstanding invoices
            outstanding_invoices = invoices.filtered(lambda inv: inv.amount_residual > 0)
            if not outstanding_invoices:
                return
            
            # Reconcile payment with invoices
            self._reconcile_batch_payment(payment, outstanding_invoices)
            
        except (ValueError, TypeError, IndexError):
            # If parsing fails, let standard reconciliation handle it
            pass
    
    def _reconcile_batch_payment(self, payment, invoices):
        """Reconcile payment across multiple invoices proportionally."""
        if not payment.move_id or not invoices:
            return
            
        # Get payment move lines
        payment_lines = payment.move_id.line_ids.filtered(
            lambda line: line.account_id == payment.destination_account_id and line.debit > 0
        )
        
        if not payment_lines:
            return
        
        # Collect receivable lines from all invoices
        receivable_lines = invoices.line_ids.filtered(
            lambda line: line.account_id.account_type == 'asset_receivable' and line.reconciled == False
        )
        
        if not receivable_lines:
            return
        
        # Reconcile payment with all outstanding receivable lines
        lines_to_reconcile = payment_lines + receivable_lines
        if len(lines_to_reconcile) > 1:
            lines_to_reconcile.reconcile()