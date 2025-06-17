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
    
    payment_transaction_id = fields.Many2one(
        comodel_name='payment.transaction',
        string='Payment Transaction',
        readonly=True,
        tracking=True,
        help='Payment transaction generated when customer pays through the link'
    )
    
    payment_method_id = fields.Many2one(
        comodel_name='payment.method',
        string='Payment Method',
        readonly=True,
        tracking=True,
        help='Payment method used by customer for the transaction'
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
    
    @api.depends('invoice_ids.amount_residual', 'invoice_ids.amount_total', 'invoice_ids.state')
    def _compute_total_amount(self):
        """Compute the total amount of all invoices in the batch."""
        for record in self:
            total = 0
            for invoice in record.invoice_ids:
                if invoice.state == 'draft':
                    # For draft invoices, use amount_total
                    total += invoice.amount_total
                else:
                    # For posted invoices, use amount_residual
                    total += invoice.amount_residual
            record.total_amount = total
    
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
    
    # Removed validation for posted invoices - draft invoices are now allowed
    
    @api.constrains('invoice_ids')
    def _check_invoices_unpaid(self):
        """Ensure all invoices have outstanding amounts."""
        for record in self:
            if record.invoice_ids:
                paid_invoices = record.invoice_ids.filtered(
                    lambda inv: inv.state == 'posted' and inv.amount_residual <= 0
                )
                if paid_invoices:
                    raise ValidationError(_(
                        'All posted invoices must have outstanding amounts. '
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
    
    def process_payment(self, payment_method=None, payment_reference=None, payment_transaction=None):
        """Process the batch payment and mark invoices as paid."""
        self.ensure_one()
        
        if self.state != 'link_generated':
            raise UserError(_('Payment can only be processed for batch payments with generated links.'))
        
        # Post draft invoices first
        draft_invoices = self.invoice_ids.filtered(lambda inv: inv.state == 'draft')
        if draft_invoices:
            for invoice in draft_invoices:
                try:
                    invoice.action_post()
                except Exception as e:
                    raise UserError(_(
                        'Failed to post draft invoice %s: %s'
                    ) % (invoice.name, str(e)))
        
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
        
        # Store payment transaction and method info
        if payment_transaction:
            self.payment_transaction_id = payment_transaction.id
            if payment_transaction.payment_method_id:
                self.payment_method_id = payment_transaction.payment_method_id.id
        elif payment_method:
            self.payment_method_id = payment_method.id
        
        self.state = 'paid'
        
        # Reconcile payment with invoices
        self._reconcile_payment_with_invoices(payment)
        
        # Log payment completion with payment method info
        payment_method_name = self.payment_method_id.name if self.payment_method_id else _('Unknown Payment Method')
        
        # Add message to batch payment chatter
        self.message_post(
            body=_('Batch payment completed. Payment amount: %s %s. The customer has selected %s to make the payment.') % (
                self.total_amount, self.currency_id.name, payment_method_name
            ),
            message_type='notification'
        )
        
        # Add similar message to each invoice chatter
        for invoice in self.invoice_ids:
            invoice.message_post(
                body=_('The customer has selected %s to make the payment') % payment_method_name,
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
        self.payment_transaction_id = False
        self.payment_method_id = False
    
    def update_payment_transaction(self, transaction_id, payment_method_id=None):
        """Update batch payment with payment transaction details."""
        self.ensure_one()
        
        if transaction_id:
            transaction = self.env['payment.transaction'].browse(transaction_id)
            if transaction.exists():
                self.payment_transaction_id = transaction.id
                
                # Get payment method from transaction or parameter
                if transaction.payment_method_id:
                    self.payment_method_id = transaction.payment_method_id.id
                elif payment_method_id:
                    self.payment_method_id = payment_method_id
                
                # Process payment if transaction is done
                if transaction.state == 'done':
                    self.process_payment(
                        payment_transaction=transaction,
                        payment_reference=transaction.reference
                    )
        
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
    
    def action_view_payment_transaction(self):
        """Open payment transaction record."""
        if not self.payment_transaction_id:
            raise UserError(_('No payment transaction found for this batch.'))
        
        return {
            'name': _('Payment Transaction'),
            'type': 'ir.actions.act_window',
            'res_model': 'payment.transaction',
            'res_id': self.payment_transaction_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
