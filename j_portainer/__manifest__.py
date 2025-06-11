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
        * API Logs & Operations Tracking
        
        Uses API Key authentication method for secure communication with Portainer.
        Exclusively uses Portainer v2 API endpoints for full compatibility with CE 2.9.0+ and 2.27.4 LTS.
        Includes comprehensive API logging system for all Portainer operations.
    """,
    'author': 'Your Company',
    'category': 'Administration',
    'depends': ['base', 'mail'],
    'data': [
        'security/portainer_security.xml',
        'security/ir.model.access.csv',
        'data/cron_data.xml',
        'data/resource_type_data.xml',
        'views/portainer_sync_schedule_views.xml',
        'views/portainer_server_views.xml',
        'views/portainer_environment_views.xml',
        'views/portainer_container_views.xml',
        'views/portainer_container_label_views.xml',
        'views/portainer_container_volume_views.xml',
        'views/portainer_container_network_views.xml',
        'views/portainer_container_env_views.xml',
        'views/portainer_container_port_views.xml',
        'views/portainer_image_views.xml',
        'views/portainer_volume_views.xml',
        'views/portainer_network_views.xml',
        'views/portainer_template_views.xml',
        'views/portainer_custom_template_views.xml',
        'views/portainer_git_credentials_views.xml',
        'views/portainer_stack_views.xml',
        'views/portainer_api_log_views.xml',
        'wizards/portainer_sync_wizard_views.xml',
        'wizards/container_logs_wizard_view.xml',
        'wizards/container_remove_wizard_view.xml',
        'wizards/image_remove_wizard_view.xml',
        'wizards/template_deploy_wizard_view.xml',
        'wizards/container_join_network_wizard_views.xml',
        'wizards/container_deploy_wizard_views.xml',
        'wizards/api_log_config_wizard_view.xml',
        'wizards/stack_migration_wizard_views.xml',
        'views/menu_views.xml',
    ],
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}