
from odoo import models, _


class AccountMove(models.Model):
    _inherit = 'account.move'
    
    def action_batch_payment_generate_link(self):
        """Server action method for generating batch payment link."""
        from odoo.exceptions import UserError
        
        # Validate selected invoices
        if not self:
            raise UserError(_('Please select at least one invoice.'))

        # Filter only customer invoices
        customer_invoices = self.filtered(lambda inv: inv.move_type == 'out_invoice')
        if not customer_invoices:
            raise UserError(_('Please select only customer invoices.'))

        # Check if all invoices belong to the same partner
        partners = customer_invoices.mapped('partner_id')
        if len(partners) > 1:
            raise UserError(_(
                'All selected invoices must belong to the same customer. '
                'Found invoices for multiple customers: %s'
            ) % ', '.join(partners.mapped('name')))

        # Check if all invoices are posted
        non_posted = customer_invoices.filtered(lambda inv: inv.state != 'posted')
        if non_posted:
            raise UserError(_(
                'All invoices must be posted before creating batch payment. '
                'Non-posted invoices: %s'
            ) % ', '.join(non_posted.mapped('name')))

        # Check if all invoices have outstanding amounts
        paid_invoices = customer_invoices.filtered(lambda inv: inv.amount_residual <= 0)
        if paid_invoices:
            raise UserError(_(
                'All invoices must have outstanding amounts. '
                'Already paid invoices: %s'
            ) % ', '.join(paid_invoices.mapped('name')))

        # Check if all invoices have the same currency
        currencies = customer_invoices.mapped('currency_id')
        if len(currencies) > 1:
            raise UserError(_(
                'All invoices must have the same currency. '
                'Found multiple currencies: %s'
            ) % ', '.join(currencies.mapped('name')))

        # Calculate total amount of all selected invoices
        total_amount = sum(customer_invoices.mapped('amount_residual'))
        
        # Create description with invoice IDs for payment reconciliation
        invoice_refs = ', '.join(customer_invoices.mapped('name'))
        description = _('Batch payment for invoices: %s [BATCH_IDS:%s]') % (
            invoice_refs, 
            ','.join(str(inv.id) for inv in customer_invoices)
        )
        
        # Create payment wizard with batch context
        return {
            'name': _('Generate Payment Link'),
            'type': 'ir.actions.act_window',
            'res_model': 'payment.link.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_amount': total_amount,
                'default_currency_id': customer_invoices[0].currency_id.id,
                'default_partner_id': customer_invoices[0].partner_id.id,
                'default_description': description,
                'default_is_batch_payment': True,
                # Don't pass active_ids to prevent single invoice processing
                'active_model': False,
                'active_ids': [],
                'active_id': False,
            }
        }
    
    def _register_payment_batch(self, payment_vals, batch_invoice_description):
        """Helper method to register payment across multiple invoices"""
        if '[BATCH_IDS:' in batch_invoice_description:
            # Extract invoice IDs from description
            start_marker = '[BATCH_IDS:'
            end_marker = ']'
            start_idx = batch_invoice_description.find(start_marker) + len(start_marker)
            end_idx = batch_invoice_description.find(end_marker, start_idx)
            
            if start_idx > len(start_marker) - 1 and end_idx > start_idx:
                invoice_ids_str = batch_invoice_description[start_idx:end_idx]
                try:
                    invoice_ids = [int(x.strip()) for x in invoice_ids_str.split(',') if x.strip()]
                    invoices = self.env['account.move'].browse(invoice_ids)
                    
                    # Return the invoice IDs for payment reconciliation
                    return invoices.ids
                except (ValueError, TypeError):
                    pass
        
        return []
