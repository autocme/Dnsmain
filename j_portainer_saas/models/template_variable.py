#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
import logging
import re

_logger = logging.getLogger(__name__)


class TemplateVariable(models.Model):
    """
    Template Variable Model
    
    This model stores extracted variables from Docker Compose templates
    with their field domain mappings to client model fields.
    """
    _name = 'saas.template.variable'
    _description = 'Template Variable'
    _order = 'variable_name'
    _rec_name = 'variable_name'
    
    # ========================================================================
    # FIELDS
    # ========================================================================
    
    variable_name = fields.Char(
        string='Variable Name',
        required=True,
        help='Variable name extracted from template (without @ prefix)'
    )
    
    field_domain = fields.Char(
        string='Field Domain',
        help='Field path on client model for variable replacement (e.g., sc_client_name, sc_client_subdomain)'
    )
    
    field_name = fields.Char(
        string='Field Name',
        readonly=True,
        help='Extracted field name from field_domain for rendering'
    )
    
    package_id = fields.Many2one(
        comodel_name='saas.package',
        string='Package',
        required=True,
        ondelete='cascade',
        help='Associated SaaS package'
    )
    
    # ========================================================================
    # CONSTRAINTS
    # ========================================================================
    
    _sql_constraints = [
        (
            'unique_variable_per_package',
            'UNIQUE(variable_name, package_id)',
            'Variable name must be unique per package.'
        ),
    ]
    
    # ========================================================================
    # BUSINESS METHODS
    # ========================================================================
    
    @api.onchange('field_domain')
    def _onchange_field_domain(self):
        """Extract field name from field_domain when it changes."""
        self._extract_field_name()
    
    def _extract_field_name(self):
        """Extract field name from field_domain patterns."""
        if not self.field_domain:
            self.field_name = ''
            return
        
        # Pattern to match field names in domain expressions
        # Examples: [("field_name", "!=", False)], ("field_name", "=", value)
        field_pattern = r'["\']([a-zA-Z_][a-zA-Z0-9_]*)["\']'
        matches = re.findall(field_pattern, self.field_domain)
        
        if matches:
            # Take the first field name found
            self.field_name = matches[0]
        else:
            # Try simpler pattern for direct field names
            simple_pattern = r'^([a-zA-Z_][a-zA-Z0-9_]*)$'
            match = re.match(simple_pattern, self.field_domain.strip())
            if match:
                self.field_name = match.group(1)
            else:
                self.field_name = ''
    
    @api.model
    def create(self, vals):
        """Override create to extract field name on creation."""
        record = super().create(vals)
        if vals.get('field_domain'):
            record._extract_field_name()
        return record
    
    def write(self, vals):
        """Override write to extract field name on update."""
        result = super().write(vals)
        if 'field_domain' in vals:
            self._extract_field_name()
        return result