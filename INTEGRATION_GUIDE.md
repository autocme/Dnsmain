# Docker Connectivity Integration Guide

This guide explains how to integrate the enhanced Docker connectivity solution with your existing Odoo modules. The solution addresses common connectivity issues and adds support for Docker API v1.49 features.

## Overview of Improvements

1. **Enhanced SSH Client**
   - Automatic connection retries
   - Better timeout handling
   - Advanced error detection and recovery

2. **Permission Handling**
   - Automatic detection of permission issues
   - Dynamic sudo mode
   - User-friendly error messages

3. **Docker API v1.49 Support**
   - BuildKit build progress tracking
   - Enhanced registry search
   - Multi-platform image support
   - Detailed build information

4. **Connectivity Framework**
   - Connection pooling for better performance
   - Command validation and cleanup
   - JSON parsing and error handling

## Integration Steps

### 1. Copy the Module Files

Add these files to your Odoo module:

- `paramiko_ssh_client.py`: Enhanced SSH client
- `docker_output_validator.py`: Docker output cleaning and validation
- `docker_permission_handler.py`: Permission detection and resolution
- `docker_api_1_49_support.py`: Docker API v1.49 features
- `enhanced_docker_connectivity.py`: Main connectivity framework

### 2. Update Your Docker Server Model

Update your Odoo Docker server model to leverage the new functionality:

```python
from odoo import models, fields, api
from .enhanced_docker_connectivity import (
    with_docker_connection,
    check_docker_server_health,
    get_api_version_info_html
)

class DockerServer(models.Model):
    _name = 'j_docker.docker_server'
    
    # Add fields for permission detection
    detected_sudo_required = fields.Boolean(
        string='Sudo Required', 
        readonly=True,
        help='Whether sudo is required for Docker commands (auto-detected)'
    )
    
    # Add fields for API version features
    api_version = fields.Char(string='API Version', readonly=True)
    api_features_html = fields.Html(string='API Features', readonly=True, sanitize=False)
    supports_api_149 = fields.Boolean(string='Supports API v1.49', readonly=True)
    
    @api.model
    def create(self, vals):
        server = super(DockerServer, self).create(vals)
        server.check_health()
        return server
    
    def check_health(self):
        """Run comprehensive health check"""
        self.ensure_one()
        
        health = check_docker_server_health(self)
        
        # Update status fields
        self.status = health['status']
        self.status_message = health['message']
        self.last_check = fields.Datetime.now()
        
        # Update permission detection fields
        if 'permissions' in health:
            self.detected_sudo_required = health['permissions'].get('sudo_required', False)
        
        # Update API version fields
        self.api_version = health.get('api_version', '')
        self.supports_api_149 = health.get('api_1_49_supported', False)
        
        # Update API features HTML
        self.api_features_html = get_api_version_info_html(self)
        
        # Update other details
        if health['details']:
            # Extract useful information
            self.docker_version = health['engine_version'] or ''
            # ... other field updates ...
            
        return health['status'] == 'online'
    
    @with_docker_connection()
    def get_containers(self, client, use_sudo=False):
        """Get containers with API-aware features"""
        from .enhanced_docker_connectivity import get_containers
        
        return get_containers(
            client, 
            all=True, 
            use_sudo=use_sudo, 
            api_version=self.api_version
        )
    
    # ... other methods using the connectivity framework ...
```

### 3. Update Your Views

Add the new fields to your Docker server form view:

```xml
<field name="api_version"/>
<field name="supports_api_149"/>
<field name="detected_sudo_required"/>

<!-- Add API version info tab -->
<page string="API Features" attrs="{'invisible': [('api_version', '=', False)]}">
    <group>
        <field name="api_features_html" widget="html" nolabel="1"/>
    </group>
</page>
```

### 4. Test Docker API v1.49 Features

Use the `docker_api_149_test.py` script to verify that the API v1.49 features are working properly:

```bash
python docker_api_149_test.py --hostname example.com --username user --password pass --sudo
```

## Using Docker API v1.49 Features

### BuildKit Build Progress Events

```python
@with_docker_connection()
def build_image_with_progress(self, client, use_sudo=False):
    from .docker_api_1_49_support import DockerApi149Support
    
    # Create build command with progress
    build_cmd = DockerApi149Support.get_buildkit_progress_command(
        tag="my-image:latest",
        context_path="/path/to/build/context",
        build_args={"VERSION": "1.0"}
    )
    
    # Execute the build command
    output = client.execute_command(build_cmd, timeout=300)
    
    # Parse progress data
    progress_data = DockerApi149Support.parse_buildkit_progress(output)
    
    return progress_data
```

### Enhanced Registry Search

```python
@with_docker_connection()
def search_registry(self, client, query, use_sudo=False):
    from .docker_api_1_49_support import DockerApi149Support
    
    # Search with filters
    search_results = DockerApi149Support.enhanced_registry_search(
        client,
        query,
        filters={"is-official": "true"},
        limit=10,
        use_sudo=use_sudo
    )
    
    return search_results
```

### Multi-Platform Images

```python
@with_docker_connection()
def get_multiplatform_images(self, client, use_sudo=False):
    from .docker_api_1_49_support import DockerApi149Support
    
    # Get multi-platform images
    images = DockerApi149Support.get_multiplatform_images(
        client,
        use_sudo=use_sudo
    )
    
    return images
```

### Enhanced Build Info

```python
@with_docker_connection()
def get_image_build_info(self, client, image_id, use_sudo=False):
    from .docker_api_1_49_support import DockerApi149Support
    
    # Get build info
    build_info = DockerApi149Support.get_build_info(
        client,
        image_id,
        use_sudo=use_sudo
    )
    
    return build_info
```

## Permission Handling

The enhanced connectivity framework automatically handles permission issues:

1. It detects if Docker commands require sudo
2. It updates the `detected_sudo_required` field on the server
3. It automatically uses sudo for commands when needed

You can also manually check for permission issues:

```python
@with_docker_connection(auto_sudo=True)
def test_permissions(self, client, use_sudo=False):
    from .docker_permission_handler import test_docker_command_permissions
    
    # Test permissions
    permission_test = test_docker_command_permissions(client, use_sudo=use_sudo)
    
    # Show permission details in the UI
    return {
        'type': 'ir.actions.client',
        'tag': 'display_notification',
        'params': {
            'title': 'Docker Permissions',
            'message': f"Direct Access: {'Yes' if permission_test['direct_access_allowed'] else 'No'}\n"
                      f"Sudo Required: {'Yes' if permission_test['requires_sudo'] else 'No'}",
            'sticky': True,
            'type': 'info'
        }
    }
```

## Troubleshooting

### Connection Issues

If you encounter connection issues:

1. Check the SSH connection parameters
2. Verify that the Docker daemon is running
3. Check permissions and sudo settings
4. Increase timeouts and retry counts if needed

### Permission Issues

If permission issues persist:

1. Add the user to the docker group: `sudo usermod -aG docker $USER`
2. Restart the Docker daemon: `sudo systemctl restart docker`
3. Log out and back in (or run `newgrp docker`)

### API Version Compatibility

If some features are not working:

1. Check the Docker API version (`docker version`)
2. Verify that the feature is available in the version
3. Use conditional code based on the `supports_api_149` field

## Testing

Use the provided test scripts to verify functionality:

- `docker_connectivity_test.py`: Test SSH and Docker basic connectivity
- `docker_api_149_test.py`: Test Docker API v1.49 specific features

Example:

```bash
python docker_connectivity_test.py --hostname server.example.com --username user --all
python docker_api_149_test.py --hostname server.example.com --username user --all
```