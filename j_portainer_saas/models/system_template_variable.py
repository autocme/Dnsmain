#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class SystemTemplateVariable(models.Model):
    """
    System Template Variable Model
    
    This model stores extracted variables from Docker Compose templates
    at the system type level with their field domain mappings to client model fields.
    """
    _name = 'system.template.variable'
    _description = 'System Template Variable'
    _order = 'stv_variable_name'
    _rec_name = 'stv_variable_name'
    
    # ========================================================================
    # FIELDS
    # ========================================================================
    
    stv_variable_name = fields.Char(
        string='Variable Name',
        required=False,
        help='Variable name extracted from template (without @ prefix and suffix)'
    )
    
    stv_field_domain = fields.Char(
        string='Field Domain',
        help='Field path on client model for variable replacement (e.g., sc_client_name, sc_client_subdomain)'
    )
    
    stv_field_name = fields.Char(
        string='Field Name',
        readonly=True,
        help='Extracted field name from field_domain for rendering'
    )
    
    stv_system_type_id = fields.Many2one(
        comodel_name='system.type',
        string='System Type',
        ondelete='cascade',
        help='Associated system type'
    )
    
    # ========================================================================
    # CONSTRAINTS
    # ========================================================================
    
    _sql_constraints = [
        (
            'unique_variable_system_type',
            'UNIQUE(stv_variable_name, stv_system_type_id)',
            'Variable name must be unique within a system type.'
        ),
    ]
    
    @api.constrains('stv_variable_name')
    def _check_variable_name_format(self):
        """Validate variable name format."""
        for record in self:
            if record.stv_variable_name:
                # Check for valid variable name format (letters, numbers, underscores)
                if not record.stv_variable_name.replace('_', '').isalnum():
                    raise ValidationError(_(
                        'Variable name "%s" can only contain letters, numbers, and underscores.'
                    ) % record.stv_variable_name)
                
                # Check for reserved names (optional)
                reserved_names = ['id', 'create_date', 'write_date', 'create_uid', 'write_uid']
                if record.stv_variable_name.lower() in reserved_names:
                    raise ValidationError(_(
                        'Variable name "%s" is reserved and cannot be used.'
                    ) % record.stv_variable_name)
    
    # ========================================================================
    # BUSINESS METHODS
    # ========================================================================
    
    @api.onchange('stv_field_domain')
    def _onchange_field_domain(self):
        """Extract field name from field domain for display purposes."""
        if self.stv_field_domain:
            # Extract the last part after the last dot (if any)
            field_parts = self.stv_field_domain.split('.')
            self.stv_field_name = field_parts[-1] if field_parts else ''
        else:
            self.stv_field_name = ''
    
    def name_get(self):
        """Custom name display for template variables."""
        result = []
        for record in self:
            name = record.stv_variable_name or 'New Variable'
            if record.stv_field_domain:
                name += f' → {record.stv_field_domain}'
            result.append((record.id, name))
        return result