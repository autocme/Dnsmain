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