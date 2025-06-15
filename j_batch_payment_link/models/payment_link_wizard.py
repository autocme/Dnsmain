from odoo import models, api


class PaymentLinkWizard(models.TransientModel):
    _inherit = 'payment.link.wizard'
    
    @api.model
    def default_get(self, fields_list):
        """Override to preserve batch payment amounts."""
        result = super().default_get(fields_list)
        
        # If batch payment context is set, use our calculated amount
        if self.env.context.get('default_is_batch_payment'):
            # Force our batch amount regardless of what parent method calculated
            if 'default_amount' in self.env.context:
                result['amount'] = self.env.context['default_amount']
            if 'default_currency_id' in self.env.context:
                result['currency_id'] = self.env.context['default_currency_id']
            if 'default_partner_id' in self.env.context:
                result['partner_id'] = self.env.context['default_partner_id']
            if 'default_description' in self.env.context:
                result['description'] = self.env.context['default_description']
        
        return result