{
    'name': 'Docker Management',
    'version': '1.0',
    'summary': 'Centralized Docker container management for multiple remote servers',
    'description': '''
        This Odoo application provides a centralized platform to manage multiple remote servers 
        and their Docker environments. It allows administrators to easily control servers, 
        deploy and monitor containers, manage images, volumes, and networks — all directly 
        from within Odoo.

        By integrating remote SSH access and Docker Engine API operations, the app simplifies 
        complex multi-server orchestration into a seamless, user-friendly interface.

        Main Features:
        --------------
        * Server Management
          - Add, edit, and monitor remote servers
          - Test SSH connectivity and resource usage (CPU, RAM, Disk, IP addresses)
        * Docker Container Management
          - List, start, stop, restart, and remove containers
          - Create new containers with custom configurations
          - View real-time status and resource consumption per container
        * Docker Image Management
          - List available images
          - Pull new images from registries
          - Remove unused images
          - Build new images from Dockerfiles remotely
        * Docker Network Management
          - List and manage Docker networks
          - Create and delete custom networks
          - Attach or detach containers from networks
        * Docker Volume Management
          - List and manage Docker volumes
          - Create new volumes and link them to containers
          - Delete unused volumes safely
        * Task Execution
          - Execute custom Docker and system commands remotely
          - Schedule routine tasks (e.g., automatic restarts, updates)
        * Logging and Monitoring
          - View server activity logs and container logs
          - Track errors and operational statuses
        * Settings
          - Manage SSH keys, server access tokens, and Docker connection settings
          - Configure system timeouts, retries, and alert preferences
    ''',
    'category': 'Operations/Docker',
    'author': 'Odoo Dev',
    'website': 'https://www.odoo.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'web',
        'nalios_ssh_clients',  # Dependency on SSH client module
        'mail',
    ],
    'data': [
        'security/docker_security.xml',
        'security/ir.model.access.csv',
        'views/docker_server_views.xml',
        'views/docker_container_views.xml',
        'views/docker_image_views.xml',
        'views/docker_network_views.xml',
        'views/docker_volume_views.xml',
        'views/docker_task_views.xml',
        'views/docker_logs_views.xml',
        'views/docker_menu.xml',
        'data/docker_data.xml',
    ],
    # Removed assets section to eliminate JS dependencies
    'demo': [
        'data/docker_demo.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'images': ['static/description/banner.png'],
    'sequence': 90,
}