# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
#
# Copyright (C) 2023 JAAH

{
    'name': 'DNS AWS Integration',
    'version': '1.0',
    'category': 'Tools',
    'summary': 'Integrate DNS Management with AWS Route 53',
    'description': """
DNS AWS Integration
==================
This module integrates the DNS Base module with AWS Route 53, allowing you to:

- Automatically sync domain and DNS record changes with AWS Route 53
- Import existing Route 53 configurations into your Odoo DNS management
- Validate DNS records against AWS Route 53 specifications
- Monitor the status of your AWS Route 53 hosted zones and records
- Manage DNS failover configurations

This module depends on the dns_base module for core DNS management functionality and
includes all necessary AWS Route 53 specific operations internally.
    """,
    'author': 'JAAH',
    'website': 'https://www.example.com',
    'depends': ['dns_base'],
    'data': [
        'security/ir.model.access.csv',
        'views/aws_actions.xml',
        'views/aws_credentials_views.xml',
        'views/route53_config_views.xml',
        'views/domain_views.xml',
        'views/dns_record_views.xml',
        'views/aws_log_views.xml',
        'views/res_config_settings.xml',
        'views/aws_menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
    'external_dependencies': {
        'python': ['boto3', 'botocore'],
    },
}
