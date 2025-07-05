#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # ========================================================================
    # SAAS CONFIGURATION FIELDS
    # ========================================================================
    
    saas_free_trial_interval_days = fields.Integer(
        string='Free Trial Interval (Days)',
        default=30,
        config_parameter='j_portainer_saas.free_trial_interval_days',
        help='Default number of days for free trial packages'
    )