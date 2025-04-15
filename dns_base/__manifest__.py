# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
#
# Copyright (C) 2023 JAAH

{
    'name': 'DNS Base',
    'version': '1.0',
    'category': 'Tools',
    'summary': 'Manage DNS domains and DNS records',
    'description': """
DNS Domain Management
====================
This module allows you to manage DNS domains and DNS records with comprehensive record type support.
For each DNS record, you can specify the record type (A, AAAA, CAA, CNAME, DS, HTTPS, MX, NAPTR, NS, PTR, SOA, SPF, SRV, SSHFP, SVCB, TLSA, TXT) and value.
Includes robust validation for each record type.
    """,
    'author': 'JAAH',
    'website': 'https://www.example.com',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'views/domain_views.xml',
        'views/dns_records_views.xml',
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
