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
        
        # Create payment.link.wizard for batch payment
        payment_wizard = self.env['payment.link.wizard'].create({
            'amount': total_amount,
            'currency_id': customer_invoices[0].currency_id.id,
            'partner_id': customer_invoices[0].partner_id.id,
            'description': _('Batch payment for invoices: %s') % ', '.join(customer_invoices.mapped('name')),
            'batch_invoice_ids': [(6, 0, customer_invoices.ids)],
            'is_batch_payment': True,
            'res_model': 'account.move',
            'res_id': customer_invoices[0].id,
        })
        
        # Return action to open the payment wizard
        return {
            'name': _('Generate Payment Link'),
            'type': 'ir.actions.act_window',
            'res_model': 'payment.link.wizard',
            'res_id': payment_wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }