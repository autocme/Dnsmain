
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
        if self.env.context.get('active_model') == 'account.move' and len(self.env.context.get('active_ids', [])) > 1:
            res['is_batch_payment'] = True
            res['batch_invoice_ids'] = [(6, 0, self.env.context.get('active_ids', []))]
            
        return res
    
    def _get_additional_create_values(self):
        """Override to set proper values for batch payments"""
        values = super()._get_additional_create_values()
        
        if self.is_batch_payment and self.batch_invoice_ids:
            # Link to the first invoice for compatibility
            values.update({
                'res_model': 'account.move',
                'res_id': self.batch_invoice_ids[0].id,
            })
            
        return values
    
    def action_generate_link(self):
        """Override to handle batch payment link generation"""
        if self.is_batch_payment and self.batch_invoice_ids:
            # Store batch invoice info in description for payment reconciliation
            invoice_names = ', '.join(self.batch_invoice_ids.mapped('name'))
            invoice_ids_str = ','.join(str(inv_id) for inv_id in self.batch_invoice_ids.ids)
            
            # Update description to include batch info
            self.description = f"Batch payment for invoices: {invoice_names} [BATCH_IDS:{invoice_ids_str}]"
            
        return super().action_generate_link()
