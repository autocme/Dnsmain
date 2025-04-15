# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
#
# Copyright (C) 2023 JAAH

from odoo import models, fields, api

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'
    
    # In Odoo 17, we should avoid using default_ prefixed fields
    # and instead use proper config_parameter fields
    aws_region = fields.Char(string="Default AWS Region", 
                            default="us-east-1",
                            config_parameter='dns_aws.default_aws_region')
    aws_credentials_id = fields.Many2one('dns.aws.credentials', 
                                        string="Default AWS Credentials",
                                        config_parameter='dns_aws.default_credentials_id')