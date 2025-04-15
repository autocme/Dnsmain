# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
#
# Copyright (C) 2023 JAAH

from . import models

def _init_aws_services(env):
    """Initialize AWS services on module installation
    
    In Odoo 17, post_init_hook functions receive the env directly.
    """
    env['aws.service']._init_aws_services()