#!/usr/bin/env python3
# -*- coding: utf-8 -*-

{
    'name': 'J Portainer SaaS',
    'version': '17.0.1.0.0',
    'category': 'Tools',
    'summary': 'SaaS integration module for J Portainer with subscription management',
    'description': """
J Portainer SaaS Integration
============================

This module extends J Portainer with SaaS functionality, providing:

* SaaS client management with subscription integration
* Template and stack management for SaaS offerings
* Partner relationship management for SaaS services
* Integration with subscription_oca for billing and subscription management

Features:
---------
* Manage SaaS clients with subscription templates
* Link Portainer stacks to customer subscriptions
* Track partner relationships for SaaS services
* Seamless integration with existing J Portainer infrastructure

Dependencies:
-------------
* j_portainer: Core Portainer integration module
* subscription_oca: OCA subscription management module
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'depends': [
        'base',
        'mail',
        'j_portainer',
        'subscription_oca',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/package_views.xml',
        'views/saas_clients_views.xml',
        'views/menu_views.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}