# -*- coding: utf-8 -*-

"""
Docker API Version Information and Compatibility Mapping

This module provides information about Docker API versions and their features,
making it easier to support multiple Docker Engine versions in client applications.

Reference: https://docs.docker.com/reference/api/engine/version-history/
"""

import logging
import json
import re
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)

# Docker API version to Engine version mapping
ENGINE_API_MAPPING = {
    "1.49": "25.0.x",
    "1.48": "24.0.x",
    "1.47": "23.0.x",
    "1.46": "23.0.0-rc.x",
    "1.45": "23.0.0-beta.x",
    "1.44": "24.0.0-alpha.x",
    "1.43": "24.0.0-alpha.x",
    "1.42": "20.10.x",
    "1.41": "20.10.x",
    "1.40": "19.x"
}

# Key features added in each API version
API_FEATURES = {
    "1.49": [
        "BuildKit build progress events",
        "Registry search enhancements",
        "Multi-platform images in resource listings",
        "Enhanced image buildinfo"
    ],
    "1.48": [
        "Added 'driver_config' payload in Swarm join-token API",
        "Checkpoint endpoints for live container migration",
        "Added `Containers` API that supports listing containers as well as detailed container info",
        "Added `/auth` endpoint for batch authentication"
    ],
    "1.47": [
        "Added `Cluster` API to administer Swarm clusters",
        "Implemented events for image references", 
        "Added health check history in health status",
        "Added image distribution credentials to BuildKit build config"
    ],
    "1.46": [
        "Added 'Annotations' field for services",
        "Added 'runtime' field for plugins",
        "Healthcheck 'test' field supports both string and array formats",
        "Improved support for OCI Runtime and Bundle for BuildKit"
    ]
}

# Commands that leverage specific API version features
API_COMMANDS = {
    "1.49": {
        "build_with_progress": "docker build --progress=plain -t test .",
        "search_with_filter": "docker search --filter is-official=true ubuntu",
        "list_multiplatform": "docker images --format '{{json .}}' | jq 'select(.Platform != null)'",
        "get_build_info": "docker buildx build --build-arg VERSION=latest --platform=linux/amd64,linux/arm64 ."
    },
    "1.48": {
        "get_swarm_join_token": "docker swarm join-token worker -q",
        "list_checkpoints": "docker checkpoint ls <container>",
        "container_api": "curl -s --unix-socket /var/run/docker.sock http://localhost/v1.48/containers/json",
        "auth_batch": "curl -s --unix-socket /var/run/docker.sock -X POST http://localhost/v1.48/auth"
    },
    "1.47": {
        "manage_swarm_cluster": "docker system info --format '{{json .Swarm.Cluster}}'",
        "check_health_history": "docker inspect --format '{{json .State.Health}}' <container>",
        "build_with_credentials": "docker buildx build --secret id=creds,src=./credentials.txt ."
    },
    "1.46": {
        "create_service_annotations": "docker service create --annotation com.example.env=prod nginx",
        "plugin_runtime": "docker plugin install --grant-all-permissions rexray/ebs:0.11.4",
        "healthcheck_array_style": "docker run --healthcheck-cmd 'curl -f http://localhost/ || exit 1' nginx"
    }
}

# Compatibility issues to watch for
API_COMPATIBILITY_NOTES = {
    "1.49": "Image build events now support detailed progress reporting from BuildKit.",
    "1.48": "Checkpoint API requires experimental features to be enabled in Docker daemon.",
    "1.47": "Health check history format changed to include timestamps for each health status change.",
    "1.46": "Service annotations require Docker Swarm mode to be enabled."
}

class DockerAPIVersion(models.AbstractModel):
    """
    Abstract model for Docker API version information and compatibility
    Used for utility methods related to Docker API versions
    """
    _name = 'docker.api.version'
    _description = 'Docker API Version Utilities'

    @api.model
    def get_api_url(self, version="1.41", endpoint=""):
        """
        Get the API URL for a specific version and endpoint.
        
        Args:
            version (str): API version (e.g., "1.41")
            endpoint (str): API endpoint (e.g., "containers/json")
            
        Returns:
            str: Complete URL for the Docker API
        """
        return f"http://localhost/v{version}/{endpoint}"

    @api.model
    def get_engine_version_for_api(self, api_version):
        """
        Get the Docker Engine version that corresponds to a specific API version.
        
        Args:
            api_version (str): API version (e.g., "1.41")
            
        Returns:
            str: Docker Engine version or None if not found
        """
        # Remove 'v' prefix if present
        if api_version.startswith('v'):
            api_version = api_version[1:]
            
        return ENGINE_API_MAPPING.get(api_version)

    @api.model
    def get_features_for_api(self, api_version):
        """
        Get the features introduced in a specific API version.
        
        Args:
            api_version (str): API version (e.g., "1.41")
            
        Returns:
            list: Features introduced in the specified API version or empty list if not found
        """
        # Remove 'v' prefix if present
        if api_version.startswith('v'):
            api_version = api_version[1:]
            
        return API_FEATURES.get(api_version, [])

    @api.model
    def get_commands_for_api(self, api_version):
        """
        Get example commands for a specific API version.
        
        Args:
            api_version (str): API version (e.g., "1.41")
            
        Returns:
            dict: Dictionary of command examples for the specified API version or empty dict if not found
        """
        # Remove 'v' prefix if present
        if api_version.startswith('v'):
            api_version = api_version[1:]
            
        return API_COMMANDS.get(api_version, {})

    @api.model
    def get_compatibility_notes(self, api_version):
        """
        Get compatibility notes for a specific API version.
        
        Args:
            api_version (str): API version (e.g., "1.41")
            
        Returns:
            str: Compatibility notes for the specified API version or None if not found
        """
        # Remove 'v' prefix if present
        if api_version.startswith('v'):
            api_version = api_version[1:]
            
        return API_COMPATIBILITY_NOTES.get(api_version)

    @api.model
    def format_curl_command(self, version, endpoint, method="GET", data=None):
        """
        Format a curl command for the Docker API.
        
        Args:
            version (str): API version (e.g., "1.41")
            endpoint (str): API endpoint (e.g., "containers/json")
            method (str): HTTP method (e.g., "GET", "POST")
            data (str): JSON data for the request body (for POST, PUT, etc.)
            
        Returns:
            str: Formatted curl command
        """
        # Remove 'v' prefix if present
        if version.startswith('v'):
            version = version[1:]
            
        cmd = f"curl -s --unix-socket /var/run/docker.sock -X {method} {self.get_api_url(version, endpoint)}"
        
        if data:
            cmd += f" -H 'Content-Type: application/json' -d '{data}'"
            
        return cmd

    @api.model
    def get_docker_api_version_info(self, server_id):
        """
        Get Docker API version information for a specific Docker server.
        
        Args:
            server_id: ID of the docker.server record
            
        Returns:
            dict: Dictionary with API version information
        """
        server = self.env['docker.server'].browse(server_id)
        if not server.exists():
            return {}
            
        api_version = server.docker_api_version
        
        # Compile information
        info = {
            'api_version': api_version,
            'engine_version': self.get_engine_version_for_api(api_version),
            'features': self.get_features_for_api(api_version),
            'compatibility_notes': self.get_compatibility_notes(api_version),
            'commands': self.get_commands_for_api(api_version)
        }
        
        return info

    @api.model
    def detect_api_version(self, server_id):
        """
        Detect Docker API version from a remote server.
        
        Args:
            server_id: ID of the docker.server record
            
        Returns:
            str: Docker API version (e.g., "1.41") or None if it couldn't be determined
        """
        server = self.env['docker.server'].browse(server_id)
        if not server.exists():
            return None
            
        try:
            # Prepare command for API version detection
            from ..models.docker_server import clean_ssh_output
            
            # Execute the Docker version command with JSON output
            ssh_client = server.ssh_client_id
            
            if not ssh_client:
                _logger.error(f"No SSH client configured for server {server.name}")
                return None
                
            # Prepare the command - with sudo if needed
            cmd = "docker version --format '{{json .Server.APIVersion}}'"
            if server.use_sudo:
                cmd = f"sudo {cmd}"
                
            # Execute the command
            output = ssh_client.execute_command(cmd)
            
            # Clean the output
            output = clean_ssh_output(output)
            
            # Try to parse as JSON - should be a simple string
            try:
                api_version = json.loads(output)
                return api_version
            except json.JSONDecodeError:
                # If not valid JSON, try to extract version with regex
                version_match = re.search(r'(\d+\.\d+)', output)
                if version_match:
                    return version_match.group(1)
                    
            return None
            
        except Exception as e:
            _logger.error(f"Error detecting Docker API version: {str(e)}")
            return None