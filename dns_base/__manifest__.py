# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
#
# Copyright (C) 2023 JAAH

{
    'name': 'DNS Base',
    'version': '1.0',
    'category': 'Tools',
    'summary': 'Manage DNS domains and subdomains',
    'description': """
DNS Domain Management
====================
This module allows you to manage DNS domains and subdomains.
For each subdomain, you can specify the value and conversion method (A or CNAME).
    """,
    'author': 'JAAH',
    'website': 'https://www.example.com',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'views/domain_views.xml',
        'views/subdomain_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
    'external_dependencies': {
        'python': ['validator_collection'],
    },
}
