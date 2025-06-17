from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class BatchPaymentWizard(models.TransientModel):
    """
    Wizard for creating batch payments from selected invoices.
    """
    _name = 'batch.payment.wizard'
    _description = 'Batch Payment Creation Wizard'

    # ========================================================================
    # FIELDS
    # ========================================================================
    
    invoice_ids = fields.Many2many(
        comodel_name='account.move',
        string='Selected Invoices',
        required=True,
        help='Invoices selected for batch payment'
    )
    
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Customer',
        compute='_compute_partner_id',
        store=True,
        readonly=True,
        help='Customer for all selected invoices'
    )
    
    total_amount = fields.Monetary(
        string='Total Amount',
        compute='_compute_total_amount',
        store=True,
        currency_field='currency_id',
        help='Total amount of all selected invoices'
    )
    
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        compute='_compute_currency_id',
        store=True,
        readonly=True,
        help='Currency of the invoices'
    )
    
    invoice_count = fields.Integer(
        string='Invoice Count',
        compute='_compute_invoice_count',
        help='Number of selected invoices'
    )
    
    notes = fields.Text(
        string='Notes',
        help='Additional notes for the batch payment'
    )
    
    # ========================================================================
    # COMPUTE METHODS
    # ========================================================================
    
    @api.depends('invoice_ids')
    def _compute_partner_id(self):
        """Compute partner from invoices."""
        for wizard in self:
            partners = wizard.invoice_ids.mapped('partner_id')
            wizard.partner_id = partners[0] if len(partners) == 1 else False
    
    @api.depends('invoice_ids')
    def _compute_total_amount(self):
        """Compute total amount from invoices."""
        for wizard in self:
            wizard.total_amount = sum(wizard.invoice_ids.mapped('amount_residual'))
    
    @api.depends('invoice_ids')
    def _compute_currency_id(self):
        """Compute currency from invoices."""
        for wizard in self:
            currencies = wizard.invoice_ids.mapped('currency_id')
            wizard.currency_id = currencies[0] if len(currencies) == 1 else False
    
    @api.depends('invoice_ids')
    def _compute_invoice_count(self):
        """Compute invoice count."""
        for wizard in self:
            wizard.invoice_count = len(wizard.invoice_ids)
    
    # ========================================================================
    # VALIDATION METHODS
    # ========================================================================
    
    @api.constrains('invoice_ids')
    def _validate_invoices(self):
        """Validate selected invoices for batch payment."""
        for wizard in self:
            if not wizard.invoice_ids:
                raise ValidationError(_('Please select at least one invoice.'))
            
            # Check if all invoices are customer invoices
            non_customer_invoices = wizard.invoice_ids.filtered(
                lambda inv: inv.move_type != 'out_invoice'
            )
            if non_customer_invoices:
                raise ValidationError(_(
                    'Only customer invoices can be included in batch payments. '
                    'Invalid invoice types found: %s'
                ) % ', '.join(non_customer_invoices.mapped('name')))
            
            # Check if all invoices belong to the same partner
            partners = wizard.invoice_ids.mapped('partner_id')
            if len(partners) > 1:
                raise ValidationError(_(
                    'All invoices must belong to the same customer. '
                    'Found invoices for multiple customers: %s'
                ) % ', '.join(partners.mapped('name')))
            
            # Check if all invoices are posted
            non_posted = wizard.invoice_ids.filtered(lambda inv: inv.state != 'posted')
            if non_posted:
                raise ValidationError(_(
                    'All invoices must be posted before creating batch payment. '
                    'Non-posted invoices: %s'
                ) % ', '.join(non_posted.mapped('name')))
            
            # Check if all invoices have outstanding amounts
            paid_invoices = wizard.invoice_ids.filtered(lambda inv: inv.amount_residual <= 0)
            if paid_invoices:
                raise ValidationError(_(
                    'All invoices must have outstanding amounts. '
                    'Already paid invoices: %s'
                ) % ', '.join(paid_invoices.mapped('name')))
            
            # Check if all invoices have the same currency
            currencies = wizard.invoice_ids.mapped('currency_id')
            if len(currencies) > 1:
                raise ValidationError(_(
                    'All invoices must have the same currency. '
                    'Found multiple currencies: %s'
                ) % ', '.join(currencies.mapped('name')))
    
    # ========================================================================
    # ACTION METHODS
    # ========================================================================
    
    def action_create_batch_payment(self):
        """Create batch payment from selected invoices."""
        self.ensure_one()
        
        # Validate invoices
        self._validate_invoices()
        
        # Create batch payment
        batch_payment_vals = {
            'partner_id': self.partner_id.id,
            'invoice_ids': [(6, 0, self.invoice_ids.ids)],
            'currency_id': self.currency_id.id,
            'notes': self.notes,
        }
        
        batch_payment = self.env['batch.payment'].create(batch_payment_vals)
        
        # Return action to open the created batch payment
        return {
            'name': _('Batch Payment'),
            'type': 'ir.actions.act_window',
            'res_model': 'batch.payment',
            'res_id': batch_payment.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_generate_link_and_create(self):
        """Create batch payment and immediately generate payment link."""
        self.ensure_one()
        
        # Create batch payment
        action = self.action_create_batch_payment()
        batch_payment = self.env['batch.payment'].browse(action['res_id'])
        
        # Generate payment link
        batch_payment.generate_payment_link()
        
        return action