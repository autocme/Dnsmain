from odoo import models, api


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'
    
    def _reconcile_after_done(self):
        """Override to handle batch payment reconciliation after transaction completion."""
        # Check if this is a batch payment transaction
        if self.reference and '[BATCH_IDS:' in self.reference:
            self._handle_batch_payment_reconciliation()
        else:
            # Use standard reconciliation for non-batch payments
            return super()._reconcile_after_done()
    
    def _handle_batch_payment_reconciliation(self):
        """Handle reconciliation for batch payment transactions."""
        try:
            # Extract invoice IDs from transaction reference
            ref = self.reference or ''
            start_marker = '[BATCH_IDS:'
            end_marker = ']'
            start_idx = ref.find(start_marker)
            end_idx = ref.find(end_marker, start_idx)
            
            if start_idx == -1 or end_idx == -1:
                return super()._reconcile_after_done()
            
            # Parse invoice IDs
            start_idx += len(start_marker)
            invoice_ids_str = ref[start_idx:end_idx]
            invoice_ids = [int(x.strip()) for x in invoice_ids_str.split(',') if x.strip().isdigit()]
            
            if not invoice_ids:
                return super()._reconcile_after_done()
            
            # Get the invoices to reconcile
            invoices = self.env['account.move'].browse(invoice_ids).exists()
            outstanding_invoices = invoices.filtered(lambda inv: inv.amount_residual > 0)
            
            if not outstanding_invoices:
                return super()._reconcile_after_done()
            
            # Create payment for the transaction amount
            payment_vals = self._prepare_batch_payment_vals(outstanding_invoices)
            if payment_vals:
                payment = self.env['account.payment'].create(payment_vals)
                payment.action_post()
                
                # The payment.create override will handle batch reconciliation
                return payment
            
        except (ValueError, TypeError, IndexError):
            # Fall back to standard reconciliation on any error
            pass
            
        return super()._reconcile_after_done()
    
    def _prepare_batch_payment_vals(self, invoices):
        """Prepare payment values for batch payment."""
        if not invoices or not self.partner_id:
            return False
            
        return {
            'amount': self.amount,
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': self.partner_id.id,
            'currency_id': self.currency_id.id,
            'payment_method_id': self.env.ref('account.account_payment_method_manual_in').id,
            'ref': self.reference,
            'date': self.create_date.date() if self.create_date else False,
        }