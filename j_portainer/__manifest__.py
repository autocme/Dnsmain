# -*- coding: utf-8 -*-
{
    'name': 'Portainer Integration',
    'version': '1.0',
    'summary': 'Odoo integration with Portainer CE',
    'description': """
        Portainer Integration System
        ===========================
        This module provides integration with Portainer Community Edition 2.27.4 LTS, 
        allowing you to sync and manage:
        
        * Containers
        * Images
        * Volumes
        * Networks
        * Application Templates
        * Custom Templates
        * Stacks
        * Environments & Host Details
        
        Uses API Key authentication method for secure communication with Portainer.
    """,
    'author': 'Your Company',
    'category': 'Administration',
    'depends': ['base', 'mail'],
    'data': [
        'security/portainer_security.xml',
        'security/ir.model.access.csv',
        'views/portainer_server_views.xml',
        'views/portainer_container_views.xml',
        'views/portainer_image_views.xml',
        'views/portainer_volume_views.xml',
        'views/portainer_network_views.xml',
        'views/portainer_template_views.xml',
        'views/portainer_stack_views.xml',
        'views/portainer_environment_views.xml',
        'views/menu_views.xml',
        'wizards/portainer_sync_wizard_views.xml',
    ],
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}