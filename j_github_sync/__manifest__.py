# -*- coding: utf-8 -*-
{
    'name': 'J GitHub Sync Server Integration',
    'version': '17.0.1.0.0',
    'category': 'Tools',
    'summary': 'Integration with GitHub Sync Server API for repository and container management',
    'description': '''
GitHub Sync Server Integration
==============================

This module provides integration with GitHub Sync Server API, allowing:

Repository Management:
- List and manage GitHub repositories
- Sync repositories manually or automatically
- Monitor repository status and updates
- Create, update, and delete repositories

Container Management:
- Discover and manage Docker containers
- Monitor container status
- Restart containers when needed

System Monitoring:
- View system logs and status
- Monitor API health and performance
- Track synchronization operations

Features:
- Secure API key authentication
- Real-time status monitoring
- Automated sync scheduling
- Comprehensive logging
- Error handling and retry mechanisms
    ''',
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'web',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/cron_data.xml',
        'views/github_sync_server_views.xml',
        'views/github_repository_views.xml',
        'views/github_sync_log_views.xml',
        'wizards/sync_config_wizard_view.xml',
        'views/menu_views.xml',
    ],
    'demo': [],
    'installable': True,
    'auto_install': False,
    'application': True,
}