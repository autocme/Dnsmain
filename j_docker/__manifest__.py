# -*- coding: utf-8 -*-
{
    'name': 'Docker Management',
    'version': '1.0',
    'summary': 'Manage Docker servers, containers, images, volumes, and networks',
    'description': """
        Comprehensive Docker Management System
        ======================================
        This module allows managing Docker servers and their resources
        through Odoo, including:
        
        * Server connection management (SSH)
        * Container operations (start, stop, restart, remove)
        * Image management (pull, remove)
        * Volume management
        * Network management
        * Command execution
        
        Full support for Docker Engine API v1.49 and Docker 28.1.1
    """,
    'author': 'Your Company',
    'category': 'Administration',
    'depends': ['base'],
    'data': [
        'security/docker_security.xml',
        'security/ir.model.access.csv',
        'views/docker_server_views.xml',
        'views/docker_container_views.xml',
        'views/docker_image_views.xml',
        'views/docker_volume_views.xml',
        'views/docker_network_views.xml',
        'views/menu_views.xml',
        'wizards/docker_command_wizard_views.xml',
    ],
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}