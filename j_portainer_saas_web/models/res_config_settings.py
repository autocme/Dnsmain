#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # ========================================================================
    # SAAS WEB CONFIGURATION FIELDS
    # ========================================================================
    
    saas_web_support_phone = fields.Char(
        string='Support Phone Number',
        config_parameter='j_portainer_saas_web.support_phone',
        help='Support phone number displayed in error messages when deployment fails or is cancelled'
    )