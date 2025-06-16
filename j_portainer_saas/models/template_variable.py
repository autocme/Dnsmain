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
        required=False,
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
        ondelete='cascade',
        help='Associated SaaS package'
    )
    
    client_id = fields.Many2one(
        comodel_name='saas.client',
        string='Client',
        ondelete='cascade',
        help='Associated SaaS client (for client-specific variable instances)'
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
        (
            'unique_variable_per_client',
            'UNIQUE(variable_name, client_id)',
            'Variable name must be unique per client.'
        ),
        (
            'package_or_client_required',
            'CHECK((package_id IS NOT NULL AND client_id IS NULL) OR (package_id IS NULL AND client_id IS NOT NULL))',
            'Variable must belong to either a package or a client, but not both.'
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
        
        # Pattern to match field names with dot notation in domain expressions
        # Examples: [("field_name", "!=", False)], ("sc_partner_id.active", "=", True)
        field_pattern = r'["\']([a-zA-Z_][a-zA-Z0-9_.]*)["\']'
        matches = re.findall(field_pattern, self.field_domain)
        
        if matches:
            # Take the first field name found (includes dot notation)
            self.field_name = matches[0]
        else:
            # Try simpler pattern for direct field names with dot notation
            simple_pattern = r'^([a-zA-Z_][a-zA-Z0-9_.]*)$'
            match = re.match(simple_pattern, self.field_domain.strip())
            if match:
                self.field_name = match.group(1)
            else:
                self.field_name = ''
    
    @api.model
    def create(self, vals):
        """Override create to extract field name on creation."""
        # Ensure field_domain is properly stored
        if 'field_domain' in vals and vals['field_domain']:
            _logger.info(f"Creating template variable with field_domain: {vals['field_domain']}")
        
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