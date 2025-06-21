#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class SystemType(models.Model):
    """
    System Type Model for J Portainer SaaS
    
    This model manages different system types that can be used to categorize
    environments and SaaS packages. Each system type can have multiple
    environments and packages associated with it for better organization
    and management of SaaS deployments.
    """
    
    _name = 'system.type'
    _description = 'System Type for SaaS Environment Organization'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'st_sequence, st_name'
    _rec_name = 'st_complete_name'

    # ========================================================================
    # FIELDS
    # ========================================================================

    st_sequence = fields.Char(
        string='Sequence',
        readonly=True,
        copy=False,
        default=lambda self: _('New'),
        tracking=True,
        help='Auto-generated sequence code for system type identification (e.g., ST00001)'
    )
    
    st_name = fields.Char(
        string='Name',
        required=True,
        translate=True,
        tracking=True,
        help='Display name of the system type (e.g., Production, Development, Testing)'
    )
    
    st_complete_name = fields.Char(
        string='Complete Name',
        compute='_compute_complete_name',
        store=True,
        tracking=True,
        help='Computed field combining sequence and name for display purposes'
    )
    
    st_description = fields.Text(
        string='Description',
        translate=True,
        tracking=True,
        help='Detailed description of this system type and its intended use'
    )
    
    st_company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
        help='Company that owns this system type configuration'
    )
    
    st_active = fields.Boolean(
        string='Active',
        default=True,
        tracking=True,
        help='Uncheck to hide this system type without deleting it'
    )

    # ========================================================================
    # ENVIRONMENT MANAGEMENT
    # ========================================================================
    
    st_environment_ids = fields.One2many(
        'j_portainer.environment',
        'system_type_id',
        string='Environments',
        tracking=True,
        help='Portainer environments associated with this system type'
    )
    
    st_environment_count = fields.Integer(
        string='Environment Count',
        compute='_compute_environment_count',
        tracking=True,
        help='Total number of environments linked to this system type'
    )

    # ========================================================================
    # DOMAIN MANAGEMENT
    # ========================================================================
    
    st_domain_id = fields.Many2one(
        'dns.domain',
        string='Domain',
        tracking=True,
        help='Primary DNS domain for this system type deployments'
    )
    
    st_brand_id = fields.Many2one(
        'saas.brand',
        string='Brand',
        tracking=True,
        help='Default SaaS brand for this system type'
    )

    # ========================================================================
    # STACK MANAGEMENT
    # ========================================================================
    
    st_stack_count = fields.Integer(
        string='Stack Count',
        compute='_compute_stack_count',
        tracking=True,
        help='Total number of stacks across all environments in this system type'
    )

    # ========================================================================
    # NOTIFICATION SETTINGS
    # ========================================================================
    
    st_send_email_on_stack_create = fields.Boolean(
        string='Email Notifications',
        default=True,
        tracking=True,
        help='Send email notifications when new stacks are created in this system type'
    )

    # ========================================================================
    # PACKAGE MANAGEMENT
    # ========================================================================
    
    st_saas_package_ids = fields.One2many(
        'saas.package',
        'pkg_system_type_id',
        string='SaaS Packages',
        tracking=True,
        help='SaaS packages that can be deployed on this system type'
    )
    
    st_saas_package_count = fields.Integer(
        string='Package Count',
        compute='_compute_package_count',
        tracking=True,
        help='Total number of SaaS packages configured for this system type'
    )

    # ========================================================================
    # COMPUTED METHODS
    # ========================================================================

    @api.depends('st_name', 'st_sequence')
    def _compute_complete_name(self):
        """Compute the complete name combining sequence and name."""
        for record in self:
            if record.st_sequence and record.st_sequence != _('New'):
                record.st_complete_name = f"{record.st_sequence} - {record.st_name or ''}"
            else:
                record.st_complete_name = record.st_name or ''

    @api.depends('st_environment_ids')
    def _compute_environment_count(self):
        """Compute the number of environments linked to this system type."""
        for record in self:
            record.st_environment_count = len(record.st_environment_ids)

    @api.depends('st_environment_ids.stack_count')
    def _compute_stack_count(self):
        """Compute the total number of stacks across all environments."""
        for record in self:
            total_stacks = 0
            for environment in record.st_environment_ids:
                total_stacks += environment.stack_count or 0
            record.st_stack_count = total_stacks

    @api.depends('st_saas_package_ids')
    def _compute_package_count(self):
        """Compute the number of SaaS packages configured for this system type."""
        for record in self:
            record.st_saas_package_count = len(record.st_saas_package_ids)

    # ========================================================================
    # CONSTRAINTS
    # ========================================================================

    _sql_constraints = [
        (
            'unique_system_type_sequence',
            'UNIQUE(st_sequence)',
            'System Type sequence must be unique.'
        ),
        (
            'unique_system_type_name_company',
            'UNIQUE(st_name, st_company_id)',
            'System Type name must be unique per company.'
        ),
    ]

    @api.constrains('st_name')
    def _check_name_format(self):
        """Validate system type name format."""
        for record in self:
            if record.st_name:
                if len(record.st_name.strip()) < 2:
                    raise ValidationError(_('System Type name must be at least 2 characters long.'))
                
                # Check for invalid characters (optional - adjust based on requirements)
                if not record.st_name.replace(' ', '').replace('-', '').replace('_', '').isalnum():
                    raise ValidationError(_('System Type name can only contain letters, numbers, spaces, hyphens, and underscores.'))

    # ========================================================================
    # CRUD METHODS
    # ========================================================================

    @api.model
    def create(self, vals):
        """Override create to generate sequence number."""
        if vals.get('st_sequence', _('New')) == _('New'):
            vals['st_sequence'] = self.env['ir.sequence'].next_by_code('system.type') or _('New')
        
        result = super().create(vals)
        
        # Log creation
        _logger.info(f"Created system type: {result.st_complete_name} (ID: {result.id})")
        
        return result

    def write(self, vals):
        """Override write to add logging for important changes."""
        result = super().write(vals)
        
        # Log important field changes
        tracked_fields = ['st_name', 'st_active', 'st_send_email_on_stack_create']
        if any(field in vals for field in tracked_fields):
            for record in self:
                _logger.info(f"Updated system type: {record.st_complete_name} (ID: {record.id})")
        
        return result

    def unlink(self):
        """Override unlink to prevent deletion of system types with linked data."""
        for record in self:
            # Check for linked environments
            if record.st_environment_ids:
                raise UserError(_(
                    'Cannot delete system type "%s" because it has %d linked environment(s). '
                    'Please remove or reassign the environments first.'
                ) % (record.st_complete_name, len(record.st_environment_ids)))
            
            # Check for linked packages
            if record.st_saas_package_ids:
                raise UserError(_(
                    'Cannot delete system type "%s" because it has %d linked SaaS package(s). '
                    'Please remove or reassign the packages first.'
                ) % (record.st_complete_name, len(record.st_saas_package_ids)))
        
        # Log deletion
        for record in self:
            _logger.info(f"Deleting system type: {record.st_complete_name} (ID: {record.id})")
        
        return super().unlink()

    # ========================================================================
    # ACTION METHODS
    # ========================================================================

    def action_view_environments(self):
        """Open environments view filtered by this system type."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Environments - %s') % self.st_complete_name,
            'res_model': 'j_portainer.environment',
            'view_mode': 'tree,form',
            'domain': [('system_type_id', '=', self.id)],
            'context': {'default_system_type_id': self.id},
            'target': 'current',
        }

    def action_view_packages(self):
        """Open SaaS packages view filtered by this system type."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('SaaS Packages - %s') % self.st_complete_name,
            'res_model': 'saas.package',
            'view_mode': 'tree,form',
            'domain': [('pkg_system_type_id', '=', self.id)],
            'context': {'default_pkg_system_type_id': self.id},
            'target': 'current',
        }

    def action_view_stacks(self):
        """Open stacks view filtered by environments of this system type."""
        self.ensure_one()
        environment_ids = self.st_environment_ids.ids
        return {
            'type': 'ir.actions.act_window',
            'name': _('Stacks - %s') % self.st_complete_name,
            'res_model': 'j_portainer.stack',
            'view_mode': 'tree,form',
            'domain': [('environment_id', 'in', environment_ids)],
            'target': 'current',
        }

    # ========================================================================
    # BUSINESS METHODS
    # ========================================================================

    def name_get(self):
        """Return display name for system type."""
        result = []
        for record in self:
            name = record.st_complete_name or record.st_name or _('New System Type')
            result.append((record.id, name))
        return result

    def toggle_active(self):
        """Toggle active state of system type."""
        for record in self:
            record.st_active = not record.st_active
