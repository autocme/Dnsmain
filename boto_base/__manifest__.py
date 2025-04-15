# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
#
# Copyright (C) 2023 JAAH

{
    'name': 'AWS Boto Base',
    'version': '1.0',
    'category': 'Tools',
    'summary': 'Base module for AWS API integration via boto3',
    'description': """
AWS Boto Base Module
====================
This module provides the foundation for AWS service integrations, 
with support for managing multiple AWS credentials through Odoo settings.

Features:
- Centralized management of AWS credentials
- Support for multiple AWS authentication methods
- Service-specific client & resource generation
- Comprehensive error handling and logging
- Security and encryption of AWS access keys
- Base models and tools for AWS service integrations
- Integration with Odoo settings
    """,
    'author': 'JAAH',
    'website': 'https://www.example.com',
    'depends': ['base', 'base_setup', 'mail'],
    'data': [
        'security/boto_security.xml',
        'security/ir.model.access.csv',
        'views/res_config_settings_views.xml',
        'views/aws_credentials_views.xml',
        'views/aws_service_views.xml',
        'views/aws_log_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
    'external_dependencies': {
        'python': ['boto3', 'botocore'],
    },
    'post_init_hook': '_init_aws_services',
}