from odoo import models, fields, api


class PaymentLinkWizard(models.TransientModel):
    _inherit = 'payment.link.wizard'
    
    @api.model
    def default_get(self, fields_list):
        """Override default_get to handle batch payment amounts correctly."""
        result = super().default_get(fields_list)
        
        # If this is a batch payment mode, preserve the amount from context
        if self.env.context.get('batch_payment_mode'):
            if 'default_amount' in self.env.context:
                result['amount'] = self.env.context['default_amount']
            if 'default_currency_id' in self.env.context:
                result['currency_id'] = self.env.context['default_currency_id']
            if 'default_partner_id' in self.env.context:
                result['partner_id'] = self.env.context['default_partner_id']
            if 'default_description' in self.env.context:
                result['description'] = self.env.context['default_description']
        
        return result