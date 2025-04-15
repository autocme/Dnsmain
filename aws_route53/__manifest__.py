# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
#
# Copyright (C) 2023 JAAH

{
    'name': 'AWS Route 53',
    'version': '1.0',
    'category': 'Tools',
    'summary': 'AWS Route 53 DNS Management',
    'description': """
AWS Route 53 Integration
========================
This module provides integration with Amazon Route 53 service, allowing you to:

- Manage hosted zones
- Create and manage DNS records
- Configure health checks
- Import existing DNS configurations from AWS
- Synchronize DNS changes with AWS

The module leverages the boto_base module for AWS credentials and API access.
    """,
    'author': 'JAAH',
    'website': 'https://www.example.com',
    'depends': ['boto_base'],
    'data': [
        'security/route53_security.xml',
        'security/ir.model.access.csv',
        'views/hosted_zone_views.xml',
        'views/dns_record_views.xml',
        'views/health_check_views.xml',
        'views/registered_domain_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}