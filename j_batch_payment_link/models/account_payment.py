from odoo import models, fields, api, _


class AccountPayment(models.Model):
    """
    Extend Account Payment to add batch payment relationships.
    """
    _inherit = 'account.payment'

    # ========================================================================
    # FIELDS
    # ========================================================================
    
    batch_payment_id = fields.Many2one(
        comodel_name='batch.payment',
        string='Batch Payment',
        readonly=True,
        help='Batch payment that created this payment record'
    )
    
    batch_invoice_ids = fields.Many2many(
        comodel_name='account.move',
        string='Batch Invoices',
        related='batch_payment_id.invoice_ids',
        readonly=True,
        help='Invoices included in the batch payment'
    )
    
    batch_invoice_count = fields.Integer(
        string='Batch Invoice Count',
        compute='_compute_batch_invoice_count',
        help='Number of invoices in the batch payment'
    )
    
    # ========================================================================
    # COMPUTE METHODS
    # ========================================================================
    
    @api.depends('batch_invoice_ids')
    def _compute_batch_invoice_count(self):
        """Compute the number of batch invoices."""
        for record in self:
            record.batch_invoice_count = len(record.batch_invoice_ids)
    
    # ========================================================================
    # ACTION METHODS
    # ========================================================================
    
    def action_view_batch_payment(self):
        """Open the batch payment record."""
        if not self.batch_payment_id:
            return False
        
        return {
            'name': _('Batch Payment'),
            'type': 'ir.actions.act_window',
            'res_model': 'batch.payment',
            'res_id': self.batch_payment_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_view_batch_invoices(self):
        """Open invoices from the batch payment."""
        if not self.batch_invoice_ids:
            return False
        
        action = self.env.ref('account.action_move_out_invoice_type').read()[0]
        action['domain'] = [('id', 'in', self.batch_invoice_ids.ids)]
        action['context'] = {'default_move_type': 'out_invoice'}
        return action