from odoo import models, fields, api


class ResPartner(models.Model):
    _inherit = 'res.partner'

    sequence = fields.Char(
        string='Sequence',
        default=lambda self: self.env['ir.sequence'].next_by_code('res.partner.sequence') or 'New',
        copy=False,
        readonly=True,
        help='Unique sequence number for this contact'
    )

    @api.model
    def create(self, vals):
        if vals.get('sequence', 'New') == 'New':
            vals['sequence'] = self.env['ir.sequence'].next_by_code('res.partner.sequence') or 'New'
        return super().create(vals)