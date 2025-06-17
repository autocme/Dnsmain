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
    _order = 'tv_variable_name'
    _rec_name = 'tv_variable_name'
    
    # ========================================================================
    # FIELDS
    # ========================================================================
    
    tv_variable_name = fields.Char(
        string='Variable Name',
        required=False,
        help='Variable name extracted from template (without @ prefix and suffix)'
    )
    
    tv_field_domain = fields.Char(
        string='Field Domain',
        help='Field path on client model for variable replacement (e.g., sc_client_name, sc_client_subdomain)'
    )
    
    tv_field_name = fields.Char(
        string='Field Name',
        readonly=True,
        help='Extracted field name from field_domain for rendering'
    )
    
    tv_package_id = fields.Many2one(
        comodel_name='saas.package',
        string='Package',
        ondelete='cascade',
        help='Associated SaaS package'
    )
    
    sc_client_id = fields.Many2one(
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
            'UNIQUE(tv_variable_name, tv_package_id)',
            'Variable name must be unique per package.'
        ),
        (
            'unique_variable_per_client',
            'UNIQUE(tv_variable_name, sc_client_id)',
            'Variable name must be unique per client.'
        ),
        (
            'package_or_client_required',
            'CHECK((tv_package_id IS NOT NULL AND sc_client_id IS NULL) OR (tv_package_id IS NULL AND sc_client_id IS NOT NULL))',
            'Variable must belong to either a package or a client, but not both.'
        ),
    ]
    
    # ========================================================================
    # BUSINESS METHODS
    # ========================================================================
    
    @api.onchange('tv_field_domain')
    def _onchange_field_domain(self):
        """Extract field name from field_domain when it changes."""
        self._extract_field_name()
    
    def _extract_field_name(self):
        """Extract field name from field_domain patterns."""
        if not self.tv_field_domain:
            self.tv_field_name = ''
            return
        
        # Pattern to match field names with dot notation in domain expressions
        # Examples: [("field_name", "!=", False)], ("sc_partner_id.active", "=", True)
        field_pattern = r'["\']([a-zA-Z_][a-zA-Z0-9_.]*)["\']'
        matches = re.findall(field_pattern, self.tv_field_domain)

        if matches:
            # Take the first field name found (includes dot notation)
            self.tv_field_name = matches[0]
        else:
            # Try simpler pattern for direct field names with dot notation
            simple_pattern = r'^([a-zA-Z_][a-zA-Z0-9_.]*)$'
            match = re.match(simple_pattern, self.tv_field_domain.strip())
            if match:
                self.tv_field_name = match.group(1)
            else:
                self.tv_field_name = ''

    @api.model
    def create(self, vals):
        """Override create to extract field name on creation."""
        # Ensure field_domain is properly stored
        if 'tv_field_domain' in vals and vals['tv_field_domain']:
            _logger.info(f"Creating template variable with field_domain: {vals['tv_field_domain']}")

        record = super().create(vals)
        if vals.get('tv_field_domain'):
            record._extract_field_name()
        return record
    
    def write(self, vals):
        """Override write to extract field name on update."""
        result = super().write(vals)
        if 'tv_field_domain' in vals:
            self._extract_field_name()
        return result