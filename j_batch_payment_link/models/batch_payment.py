import uuid
import hashlib
from datetime import datetime, timedelta

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class BatchPayment(models.Model):
    """
    Batch Payment Model for handling multiple invoice payments through a single link.
    """
    _name = 'batch.payment'
    _description = 'Batch Payment Link'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'
    _rec_name = 'name'

    # ========================================================================
    # FIELDS
    # ========================================================================
    
    name = fields.Char(
        string='Batch Payment Reference',
        required=True,
        default=lambda self: self._get_default_name(),
        tracking=True,
        help='Unique reference for this batch payment'
    )
    
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Customer',
        required=True,
        tracking=True,
        help='Customer who will make the payment for all invoices'
    )
    
    invoice_ids = fields.Many2many(
        comodel_name='account.move',
        relation='batch_payment_invoice_rel',
        column1='batch_payment_id',
        column2='invoice_id',
        string='Invoices',
        required=True,
        tracking=True,
        help='Invoices included in this batch payment'
    )
    
    invoice_count = fields.Integer(
        string='Invoice Count',
        compute='_compute_invoice_count',
        store=True,
        help='Number of invoices in this batch payment'
    )
    
    total_amount = fields.Monetary(
        string='Total Amount',
        compute='_compute_total_amount',
        store=True,
        currency_field='currency_id',
        tracking=True,
        help='Total amount of all invoices in this batch'
    )
    
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        required=True,
        default=lambda self: self.env.company.currency_id,
        tracking=True,
        help='Currency for the batch payment'
    )
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('link_generated', 'Link Generated'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True,
       help='Current status of the batch payment')
    
    payment_link = fields.Char(
        string='Payment Link',
        readonly=True,
        tracking=True,
        help='Generated payment link to send to customer'
    )
    
    payment_token = fields.Char(
        string='Payment Token',
        readonly=True,
        help='Unique token for payment verification'
    )
    
    payment_id = fields.Many2one(
        comodel_name='account.payment',
        string='Payment Record',
        readonly=True,
        tracking=True,
        help='Payment record created when customer pays'
    )
    
    payment_date = fields.Datetime(
        string='Payment Date',
        readonly=True,
        tracking=True,
        help='Date and time when payment was made'
    )
    
    expiry_date = fields.Datetime(
        string='Link Expiry Date',
        default=lambda self: fields.Datetime.now() + timedelta(days=30),
        tracking=True,
        help='Date when the payment link expires'
    )
    
    notes = fields.Text(
        string='Notes',
        help='Additional notes for this batch payment'
    )
    
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        help='Company for this batch payment'
    )
    
    # ========================================================================
    # COMPUTE METHODS
    # ========================================================================
    
    @api.depends('invoice_ids')
    def _compute_invoice_count(self):
        """Compute the number of invoices in the batch."""
        for record in self:
            record.invoice_count = len(record.invoice_ids)
    
    @api.depends('invoice_ids.amount_residual')
    def _compute_total_amount(self):
        """Compute the total amount of all invoices in the batch."""
        for record in self:
            record.total_amount = sum(record.invoice_ids.mapped('amount_residual'))
    
    # ========================================================================
    # DEFAULT METHODS
    # ========================================================================
    
    def _get_default_name(self):
        """Generate default batch payment name."""
        return self.env['ir.sequence'].next_by_code('batch.payment') or _('New Batch Payment')
    
    # ========================================================================
    # CONSTRAINT METHODS
    # ========================================================================
    
    @api.constrains('invoice_ids')
    def _check_invoices_same_partner(self):
        """Ensure all invoices belong to the same partner."""
        for record in self:
            if record.invoice_ids:
                partners = record.invoice_ids.mapped('partner_id')
                if len(partners) > 1:
                    raise ValidationError(_(
                        'All invoices must belong to the same customer. '
                        'Found invoices for: %s'
                    ) % ', '.join(partners.mapped('name')))
                
                # Auto-set partner if not set
                if not record.partner_id and len(partners) == 1:
                    record.partner_id = partners[0]
    
    @api.constrains('invoice_ids')
    def _check_invoices_posted(self):
        """Ensure all invoices are posted."""
        for record in self:
            if record.invoice_ids:
                non_posted = record.invoice_ids.filtered(lambda inv: inv.state != 'posted')
                if non_posted:
                    raise ValidationError(_(
                        'All invoices must be posted before creating batch payment. '
                        'Non-posted invoices: %s'
                    ) % ', '.join(non_posted.mapped('name')))
    
    @api.constrains('invoice_ids')
    def _check_invoices_unpaid(self):
        """Ensure all invoices have outstanding amounts."""
        for record in self:
            if record.invoice_ids:
                paid_invoices = record.invoice_ids.filtered(lambda inv: inv.amount_residual <= 0)
                if paid_invoices:
                    raise ValidationError(_(
                        'All invoices must have outstanding amounts. '
                        'Already paid invoices: %s'
                    ) % ', '.join(paid_invoices.mapped('name')))
    
    # ========================================================================
    # BUSINESS METHODS
    # ========================================================================
    
    def generate_payment_link(self):
        """Generate payment link for the batch."""
        self.ensure_one()
        
        if self.state != 'draft':
            raise UserError(_('Payment link can only be generated for draft batch payments.'))
        
        # Generate unique access token
        token_data = f"{self.id}-{self.partner_id.id}-{datetime.now().isoformat()}"
        self.payment_token = hashlib.sha256(token_data.encode()).hexdigest()
        
        # Get the first invoice for the payment link (as reference)
        first_invoice = self.invoice_ids[0] if self.invoice_ids else False
        if not first_invoice:
            raise UserError(_('No invoices found for batch payment.'))
        
        # Generate payment link using Odoo's payment format
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        self.payment_link = f"{base_url}/payment/pay?amount={self.total_amount}&access_token={self.payment_token}"
        
        self.state = 'link_generated'
        
        # Log the link generation
        self.message_post(
            body=_('Payment link generated: %s') % self.payment_link,
            message_type='notification'
        )
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Payment Link Generated'),
                'message': _('Payment link has been generated successfully.'),
                'type': 'success',
                'sticky': False,
            }
        }
    
    def process_payment(self, payment_method=None, payment_reference=None):
        """Process the batch payment and mark invoices as paid."""
        self.ensure_one()
        
        if self.state != 'link_generated':
            raise UserError(_('Payment can only be processed for batch payments with generated links.'))
        
        # Create payment record
        payment_vals = {
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': self.partner_id.id,
            'amount': self.total_amount,
            'currency_id': self.currency_id.id,
            'date': fields.Date.today(),
            'ref': f'Batch Payment - {self.name}',
            'journal_id': self._get_default_journal().id,
        }
        
        if payment_reference:
            payment_vals['ref'] = f"{payment_vals['ref']} - {payment_reference}"
        
        payment = self.env['account.payment'].create(payment_vals)
        payment.action_post()
        
        # Link payment to batch
        payment.batch_payment_id = self.id
        self.payment_id = payment.id
        self.payment_date = fields.Datetime.now()
        self.state = 'paid'
        
        # Reconcile payment with invoices
        self._reconcile_payment_with_invoices(payment)
        
        # Log payment completion
        self.message_post(
            body=_('Batch payment completed. Payment amount: %s %s') % (
                self.total_amount, self.currency_id.name
            ),
            message_type='notification'
        )
        
        return payment
    
    def _get_default_journal(self):
        """Get default payment journal."""
        journal = self.env['account.journal'].search([
            ('type', '=', 'bank'),
            ('company_id', '=', self.company_id.id)
        ], limit=1)
        
        if not journal:
            journal = self.env['account.journal'].search([
                ('type', '=', 'cash'),
                ('company_id', '=', self.company_id.id)
            ], limit=1)
        
        if not journal:
            raise UserError(_('No payment journal found. Please configure a bank or cash journal.'))
        
        return journal
    
    def _reconcile_payment_with_invoices(self, payment):
        """Reconcile payment with batch invoices."""
        # Get receivable lines from invoices
        invoice_lines = self.invoice_ids.line_ids.filtered(
            lambda line: line.account_id.account_type == 'asset_receivable' and line.amount_residual > 0
        )
        
        # Get payment line
        payment_lines = payment.line_ids.filtered(
            lambda line: line.account_id.account_type == 'asset_receivable'
        )
        
        # Reconcile
        if invoice_lines and payment_lines:
            (invoice_lines + payment_lines).reconcile()
    
    def cancel_batch_payment(self):
        """Cancel the batch payment."""
        self.ensure_one()
        
        if self.state == 'paid':
            raise UserError(_('Cannot cancel a paid batch payment.'))
        
        self.state = 'cancelled'
        self.message_post(
            body=_('Batch payment cancelled'),
            message_type='notification'
        )
    
    def reset_to_draft(self):
        """Reset batch payment to draft."""
        self.ensure_one()
        
        if self.state == 'paid':
            raise UserError(_('Cannot reset a paid batch payment to draft.'))
        
        self.state = 'draft'
        self.payment_link = False
        self.payment_token = False
        
    # ========================================================================
    # ACTION METHODS
    # ========================================================================
    
    def action_view_invoices(self):
        """Open invoices in tree view."""
        action = self.env.ref('account.action_move_out_invoice_type').read()[0]
        action['domain'] = [('id', 'in', self.invoice_ids.ids)]
        action['context'] = {'default_move_type': 'out_invoice'}
        return action
    
    def action_view_payment(self):
        """Open payment record."""
        if not self.payment_id:
            raise UserError(_('No payment record found for this batch.'))
        
        return {
            'name': _('Payment'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'res_id': self.payment_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_send_payment_link(self):
        """Send payment link via email."""
        self.ensure_one()
        
        if not self.payment_link:
            raise UserError(_('Please generate payment link first.'))
        
        # You can customize this to use email templates
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Payment Link'),
                'message': _('Payment link: %s') % self.payment_link,
                'type': 'info',
                'sticky': True,
            }
        }