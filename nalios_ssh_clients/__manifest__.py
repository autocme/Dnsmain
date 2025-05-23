# -*- coding: utf-8 -*-
{
    'name': "SSH Manager",

    'summary': """
        Manage your SSH Clients directly from Odoo""",

    'description': """
        Manage your SSH Clients directly from Odoo by registering them in the configuration and connect to them / send commands.
        Also create routines to send a group of commands to an SSH Client to avoid having to write them every time.
    """,

    'author': "Nalios",
    'website': "https://nalios.be",
    'license': "OPL-1",
    'category': 'Administration',
    'version': '17.0',
    'price': 49.00,
    'currency': 'EUR',
    'images': ['static/description/main_screenshot.png',],
    'support': 'lop@nalios.be',
    'depends': ['base'],
    'external_dependencies': {'python': [
        'paramiko',
        'webssh',
        'tornado',
        'ansi2html'
    ]},
    'data': [
        'security/res_groups.xml',
        'security/ir.model.access.csv',
        'views/ssh_manager_views.xml',
        'views/ssh_saved_command_views.xml',
        'views/templates/webssh_templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'nalios_ssh_clients/static/src/css/ssh_manager.css',
            'nalios_ssh_clients/static/src/js/ssh_manager.js',
            'nalios_ssh_clients/static/src/js/webssh_client.js',
            'nalios_ssh_clients/static/src/xml/ssh_manager.xml',
        ],
    }
}
