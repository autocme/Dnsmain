#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api


class PortainerEnvironmentInherit(models.Model):
    """
    Inheritance of Portainer Environment for System Type Integration
    
    This model extends the j_portainer.environment model to add
    system type relationship for better organization and management
    of environments within the SaaS framework.
    """
    
    _inherit = 'j_portainer.environment'

    # ========================================================================
    # SYSTEM TYPE INTEGRATION
    # ========================================================================
    
    system_type_id = fields.Many2one(
        'system.type',
        string='System Type',
        tracking=True,
        help='System type this environment belongs to (e.g., Production, Development, Testing)'
    )