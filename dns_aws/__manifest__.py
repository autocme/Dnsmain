# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
#
# Copyright (C) 2023 JAAH

{
    'name': 'DNS AWS Route 53 Integration',
    'version': '1.0',
    'category': 'Tools',
    'summary': 'Manage DNS records via AWS Route 53',
    'description': """
DNS AWS Route 53 Integration
============================
This module integrates with AWS Route 53 to update DNS records when 
subdomains are modified in Odoo.

Features:
- Integration with AWS Route 53 API
- Automatic updating of DNS records in Route 53 hostzones
- Configuration for AWS credentials and settings
    """,
    'author': 'JAAH',
    'website': 'https://www.example.com',
    'depends': ['dns_base'],
    'data': [
        'security/ir.model.access.csv',
        'views/route53_config_views.xml',
        'views/domain_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
    'external_dependencies': {
        'python': ['boto3'],
    },
}