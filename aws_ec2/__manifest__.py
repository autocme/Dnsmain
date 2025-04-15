# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
#
# Copyright (C) 2023 JAAH

{
    'name': 'AWS EC2',
    'version': '1.0',
    'category': 'Tools',
    'summary': 'AWS EC2 Instance Management',
    'description': """
AWS EC2 Integration
===================
This module provides integration with Amazon EC2 service, allowing you to:

- Manage EC2 instances
- Work with AMIs (Amazon Machine Images)
- Configure VPCs and subnets
- Manage security groups and key pairs
- Monitor instance statuses
- Control network infrastructure
- Handle AWS EC2 resources with full lifecycle management

The module leverages the boto_base module for AWS credentials and API access.
    """,
    'author': 'JAAH',
    'website': 'https://www.example.com',
    'depends': ['boto_base'],
    'data': [
        'security/ec2_security.xml',
        'security/ir.model.access.csv',
        'views/instance_views.xml',
        'views/image_views.xml',
        'views/vpc_views.xml',
        'views/subnet_views.xml',
        'views/security_group_views.xml',
        'views/key_pair_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}