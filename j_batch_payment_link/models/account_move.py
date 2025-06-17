from odoo import models, fields, api, _


class AccountMove(models.Model):
    """
    Extend Account Move (Invoice) to add batch payment functionality.
    """
    _inherit = 'account.move'

    # ========================================================================
    # FIELDS
    # ========================================================================
    
    batch_payment_ids = fields.Many2many(
        comodel_name='batch.payment',
        relation='batch_payment_invoice_rel',
        column1='invoice_id',
        column2='batch_payment_id',
        string='Batch Payments',
        help='Batch payments that include this invoice'
    )
    
    batch_payment_count = fields.Integer(
        string='Batch Payment Count',
        compute='_compute_batch_payment_count',
        help='Number of batch payments including this invoice'
    )
    
    # ========================================================================
    # COMPUTE METHODS
    # ========================================================================
    
    @api.depends('batch_payment_ids')
    def _compute_batch_payment_count(self):
        """Compute the number of batch payments for this invoice."""
        for record in self:
            record.batch_payment_count = len(record.batch_payment_ids)
    
    # ========================================================================
    # ACTION METHODS
    # ========================================================================
    
    def action_view_batch_payments(self):
        """Open batch payments that include this invoice."""
        action = self.env.ref('j_batch_payment_link.action_batch_payment').read()[0]
        
        if len(self.batch_payment_ids) == 1:
            action['views'] = [(False, 'form')]
            action['res_id'] = self.batch_payment_ids.id
        else:
            action['domain'] = [('id', 'in', self.batch_payment_ids.ids)]
            
        return action
    
    def action_create_batch_payment(self):
        """Create batch payment for selected invoices."""
        return {
            'name': _('Create Batch Payment'),
            'type': 'ir.actions.act_window',
            'res_model': 'batch.payment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_invoice_ids': [(6, 0, self.ids)],
                'active_ids': self.ids,
                'active_model': 'account.move',
            }
        }
    
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

        # Open wizard to create batch payment
        return {
            'name': _('Create Batch Payment'),
            'type': 'ir.actions.act_window',
            'res_model': 'batch.payment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_invoice_ids': [(6, 0, customer_invoices.ids)],
                'active_ids': customer_invoices.ids,
                'active_model': 'account.move',
            }
        }