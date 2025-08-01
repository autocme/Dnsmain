#!/usr/bin/env python3
# -*- coding: utf-8 -*-
{
    'name': 'J Portainer SaaS Web',
    'version': '17.0.1.0.0',
    'category': 'Website/eCommerce',
    'summary': 'Modern website integration for SaaS package pricing and sales',
    'description': """
J Portainer SaaS Web Integration
===============================

This module provides elegant website integration for selling SaaS packages with modern pricing displays.

Key Features:
* Modern pricing snippet with Odoo-style design
* Monthly/Yearly billing toggle switch
* Dynamic styling options for brand customization
* Free trial button visibility based on package configuration
* Responsive design for all devices
* Easy-to-use snippet options panel

The snippet dynamically loads all available SaaS packages and displays them in a professional,
conversion-optimized layout similar to Odoo's official pricing structure.
    """,
    'author': 'J Portainer Development Team',
    'website': 'https://github.com/jportainer',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'website',
        'j_portainer_saas',
        'payment',
    ],
    'data': [
        'views/snippets.xml',
        'views/snippet_options.xml',
        'views/res_config_settings_views.xml',
        'templates/legal_agreement_snippet.xml',
        'templates/purchase_confirm.xml',
        'templates/invoice_payment_wizard.xml',
        'templates/payment_success_redirect.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'j_portainer_saas_web/static/src/css/pricing_snippet.css',
            'j_portainer_saas_web/static/src/js/pricing_snippet_simple.js',
            'j_portainer_saas_web/static/src/css/purchase_confirm.css',
            'j_portainer_saas_web/static/src/js/purchase_confirm.js',
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': False,
}