#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
import logging

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