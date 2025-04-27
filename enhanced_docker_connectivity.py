#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Enhanced Docker Connectivity Module

This module combines all connectivity improvements:
1. Connection pooling and retries
2. Permission handling and automatic sudo
3. Docker API 1.49 feature support
4. Improved error handling and validation

For use with Odoo Docker management modules
"""

import os
import time
import json
import logging
import socket
from typing import Dict, List, Any, Tuple, Optional
from functools import wraps

# Import the SSH client module
from paramiko_ssh_client import ParamikoSshClient

# Import Docker output validation
from docker_output_validator import (
    clean_docker_output,
    validate_docker_info,
    extract_json_from_output,
    is_docker_running
)

# Import permission handling
from docker_permission_handler import (
    detect_permission_error,
    handle_permission_issue,
    test_docker_command_permissions
)

# Import API 1.49 support
from docker_api_1_49_support import DockerApi149Support

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Connection pool
CONNECTION_POOL = {}

def get_connection(hostname, username, port=22, password=None, key_file=None, 
                   key_data=None, key_password=None, force_new=False):
    """
    Get or create an SSH connection from the pool
    
    Args:
        hostname (str): SSH server hostname
        username (str): SSH username
        port (int): SSH port
        password (str): SSH password
        key_file (str): Path to SSH key file
        key_data (str): SSH key data as string
        key_password (str): SSH key password
        force_new (bool): Force a new connection even if one exists
        
    Returns:
        ParamikoSshClient: Connected SSH client
    """
    connection_key = f"{username}@{hostname}:{port}"
    
    # Check if we have a valid connection in the pool
    if not force_new and connection_key in CONNECTION_POOL:
        client = CONNECTION_POOL[connection_key]
        
        # Test if the connection is still valid
        try:
            test_output = client.execute_command("echo 'connection_test'", timeout=5)
            if 'connection_test' in test_output:
                logger.debug(f"Reusing existing connection for {connection_key}")
                return client
        except Exception as e:
            logger.warning(f"Existing connection for {connection_key} is stale: {str(e)}")
            # Continue to create a new connection
    
    # Create a new connection
    logger.info(f"Creating new connection for {connection_key}")
    client = ParamikoSshClient(
        hostname=hostname,
        username=username,
        port=port,
        password=password,
        key_file=key_file,
        key_data=key_data,
        key_password=key_password,
        use_clean_output=True,  # Always use clean output for Docker commands
        force_minimal_terminal=True,  # Use minimal terminal to prevent ANSI codes
        connect_timeout=15,  # Slightly longer timeout for initial connection
        command_timeout=60,  # Default command timeout
        retry_count=3,       # Default retry count
        retry_delay=2        # Default delay between retries
    )
    
    # Connect to the server
    if client.connect():
        # Store in the connection pool
        CONNECTION_POOL[connection_key] = client
        return client
    else:
        logger.error(f"Failed to connect to {connection_key}")
        return None

def with_docker_connection(max_retries=3, retry_delay=2, timeout=60, auto_sudo=True):
    """
    Decorator for functions that need a Docker connection
    
    This decorator handles connection errors and retries automatically.
    
    Args:
        max_retries (int): Maximum number of retries
        retry_delay (int): Delay in seconds between retries
        timeout (int): Command timeout in seconds
        auto_sudo (bool): Automatically try sudo if permission denied
        
    Returns:
        function: Decorated function
    """
    def decorator(func):
        @wraps(func)
        def wrapper(server, *args, **kwargs):
            # Get connection parameters from server
            hostname = server.hostname
            port = server.ssh_port or 22
            username = server.username
            password = server.password
            key_file = server.key_file_path if hasattr(server, 'key_file_path') else None
            key_data = server.private_key if hasattr(server, 'private_key') else None
            use_sudo = getattr(server, 'use_sudo', False)
            
            # Set use_sudo from auto detection if enabled
            if auto_sudo:
                detected_sudo = getattr(server, 'detected_sudo_required', None)
                if detected_sudo is not None:
                    use_sudo = detected_sudo
            
            # Inject sudo parameter to the function
            kwargs['use_sudo'] = use_sudo
            
            # Track attempts
            attempts = 0
            last_error = None
            
            while attempts <= max_retries:
                if attempts > 0:
                    # Calculate exponential backoff delay
                    current_delay = retry_delay * (2 ** (attempts - 1))
                    logger.info(f"Retrying Docker operation (attempt {attempts}/{max_retries}), waiting {current_delay}s...")
                    time.sleep(current_delay)
                
                # Get a connection
                force_new = attempts > 0  # Force new connection on retry
                client = get_connection(
                    hostname=hostname,
                    username=username,
                    port=port,
                    password=password,
                    key_file=key_file,
                    key_data=key_data,
                    force_new=force_new
                )
                
                if not client:
                    attempts += 1
                    last_error = "Failed to establish SSH connection"
                    continue
                
                try:
                    # Test Docker connectivity first
                    if not test_docker_connectivity(client, use_sudo=use_sudo):
                        attempts += 1
                        last_error = "Docker daemon not accessible"
                        continue
                    
                    # Execute the actual function with the client
                    result = func(server, client, *args, **kwargs)
                    return result
                    
                except socket.timeout:
                    attempts += 1
                    last_error = "Connection timed out"
                    logger.warning(f"Docker operation timed out (attempt {attempts}/{max_retries})")
                except Exception as e:
                    attempts += 1
                    last_error = str(e)
                    logger.warning(f"Docker operation failed: {str(e)} (attempt {attempts}/{max_retries})")
            
            # All retries failed
            logger.error(f"Docker operation failed after {max_retries} retries. Last error: {last_error}")
            if hasattr(server, 'update_server_status'):
                server.update_server_status('offline', f"Failed after {max_retries} retries: {last_error}")
            return None
        
        return wrapper
    
    return decorator

def test_docker_connectivity(client, use_sudo=False):
    """
    Test if Docker is accessible via the SSH connection
    
    Args:
        client (ParamikoSshClient): SSH client
        use_sudo (bool): Whether to use sudo
        
    Returns:
        bool: True if Docker is accessible
    """
    try:
        # Run a simple Docker command
        cmd = "docker ps" if not use_sudo else "sudo docker ps"
        output = client.execute_command(cmd, timeout=10)
        
        # Check for permission issues and try sudo if needed
        if detect_permission_error(output) and not use_sudo:
            logger.info("Detected permission issue, trying with sudo")
            output = client.execute_command("sudo docker ps", timeout=10)
        
        return is_docker_running(output)
    except Exception as e:
        logger.warning(f"Docker connectivity test failed: {str(e)}")
        return False

def run_docker_command(client, command, format_json=True, use_sudo=False, timeout=60, 
                       handle_permissions=True, api_version=None):
    """
    Run a Docker command with proper formatting, permission handling and API version support
    
    Args:
        client (ParamikoSshClient): SSH client
        command (str): Docker command to run (without 'docker' prefix)
        format_json (bool): Add --format '{{json .}}' to the command
        use_sudo (bool): Prefix the command with sudo
        timeout (int): Command timeout in seconds
        handle_permissions (bool): Handle permission issues automatically
        api_version (str): Docker API version
        
    Returns:
        tuple: (success, result) where result is parsed JSON if successful or error message
    """
    # Construct the full command
    full_command = "docker " + command
    
    # Add JSON formatting if requested and appropriate
    if format_json and not command.endswith("--format '{{json .}}'") and ('inspect' in command or 'ls' in command):
        # Only add JSON formatting for commands that support it
        full_command += " --format '{{json .}}'"
    
    # Add sudo if requested
    if use_sudo:
        full_command = "sudo " + full_command
    
    logger.debug(f"Running Docker command: {full_command}")
    
    try:
        # Execute the command
        output = client.execute_command(full_command, timeout=timeout)
        
        # Check for permission issues if handling is enabled
        if handle_permissions and detect_permission_error(output):
            logger.info("Detected permission issue, handling automatically")
            success, result = handle_permission_issue(client, full_command, output)
            if success:
                # Permission issue resolved, use the new result
                output = result
        
        # Check for common error patterns
        if "Error:" in output or "error:" in output.lower():
            error_lines = [line for line in output.split('\n') if 'error' in line.lower()]
            error_message = error_lines[0] if error_lines else "Unknown Docker error"
            return False, error_message
        
        if format_json:
            # Try to parse as JSON
            json_data, error = extract_json_from_output(output, full_command)
            if json_data:
                return True, json_data
            elif error:
                return False, error
        
        # Return as text if not JSON or JSON parsing failed
        return True, clean_docker_output(output, full_command)
        
    except Exception as e:
        logger.error(f"Error executing Docker command: {str(e)}")
        return False, str(e)

def get_docker_version(client, use_sudo=False):
    """
    Get Docker version information
    
    Args:
        client (ParamikoSshClient): SSH client
        use_sudo (bool): Whether to use sudo for the command
        
    Returns:
        dict: Version information or None if failed
    """
    success, result = run_docker_command(client, "version --format '{{json .}}'", 
                                        format_json=False, use_sudo=use_sudo)
    
    if success and isinstance(result, str):
        try:
            return json.loads(result)
        except (json.JSONDecodeError, ValueError):
            # Try without json formatting
            success, result = run_docker_command(client, "version", 
                                              format_json=False, use_sudo=use_sudo)
            
            if success:
                # Parse the text output
                version_info = {'Server': {}, 'Client': {}}
                current_section = None
                
                for line in result.split('\n'):
                    line = line.strip()
                    if not line:
                        continue
                    
                    # Check for section headers
                    if line.startswith('Client:') or line == 'Client:':
                        current_section = 'Client'
                        continue
                    elif line.startswith('Server:') or line == 'Server:':
                        current_section = 'Server'
                        continue
                    
                    # Parse key-value pairs within sections
                    if current_section and ':' in line:
                        key, value = line.split(':', 1)
                        key = key.strip()
                        value = value.strip()
                        
                        # Handle nested sections like Engine:
                        if value == '' and not line.startswith(' '):
                            current_subsection = key
                            version_info[current_section][current_subsection] = {}
                        elif key.startswith(' ') and current_subsection:
                            # This is an indented key in a subsection
                            subkey = key.strip()
                            version_info[current_section][current_subsection][subkey] = value
                        else:
                            # Regular key-value in the current section
                            version_info[current_section][key] = value
                
                return version_info
    
    return None

def get_docker_info(client, use_sudo=False):
    """
    Get Docker info with validation
    
    Args:
        client (ParamikoSshClient): SSH client
        use_sudo (bool): Whether to use sudo
        
    Returns:
        dict: Docker info as dictionary or None if failed
    """
    try:
        # Run docker info with format=json if possible (newer Docker versions)
        success, result = run_docker_command(
            client,
            "info --format '{{json .}}'",
            format_json=False,
            use_sudo=use_sudo
        )
        
        if success:
            # Check if output is valid JSON
            try:
                info = json.loads(result.strip())
                return info
            except (json.JSONDecodeError, ValueError):
                # Try the regular docker info command
                success, result = run_docker_command(
                    client,
                    "info",
                    format_json=False,
                    use_sudo=use_sudo
                )
                
                if success:
                    is_valid, message = validate_docker_info(result)
                    
                    if not is_valid:
                        logger.warning(f"Invalid docker info output: {message}")
                        return None
                    
                    # Parse the text output into a dictionary
                    info = {}
                    current_section = None
                    current_subsection = None
                    
                    for line in clean_docker_output(result).split('\n'):
                        line = line.strip()
                        if not line:
                            continue
                        
                        # Check if this is a main section
                        if ':' in line and not line.startswith(' '):
                            key, value = line.split(':', 1)
                            key = key.strip()
                            value = value.strip()
                            
                            # Handle empty values (section headers)
                            if not value:
                                current_section = key
                                info[current_section] = {}
                                current_subsection = None
                                continue
                            
                            # Convert numeric values
                            if value.isdigit():
                                value = int(value)
                            
                            info[key] = value
                            current_section = key
                            current_subsection = None
                            
                        # Sub-items in a section (indented)
                        elif current_section and line.startswith(' '):
                            # Further indented items (sub-subsections)
                            if line.startswith('  ') and ':' in line:
                                # This is a deeper level
                                if current_subsection:
                                    key, value = line.split(':', 1)
                                    key = key.strip()
                                    value = value.strip()
                                    
                                    # Ensure the subsection is a dict
                                    if not isinstance(info[current_section].get(current_subsection), dict):
                                        info[current_section][current_subsection] = {}
                                    
                                    # Convert numeric values
                                    if value.isdigit():
                                        value = int(value)
                                        
                                    info[current_section][current_subsection][key] = value
                            
                            # First level indented items
                            elif ':' in line:
                                key, value = line.split(':', 1)
                                key = key.strip()
                                value = value.strip()
                                
                                # Handle empty values (subsection headers)
                                if not value and not key.startswith(' '):
                                    current_subsection = key
                                    if isinstance(info.get(current_section), dict):
                                        info[current_section][current_subsection] = {}
                                    continue
                                
                                # Ensure the current section is a dict
                                if not isinstance(info.get(current_section), dict):
                                    info[current_section] = {}
                                    
                                # Convert numeric values
                                if value.isdigit():
                                    value = int(value)
                                    
                                info[current_section][key] = value
                                current_subsection = None
                    
                    return info
        
        return None
    
    except Exception as e:
        logger.error(f"Failed to get Docker info: {str(e)}")
        return None

def check_docker_server_health(server):
    """
    Comprehensive Docker server health check including permission detection
    
    Args:
        server: Docker server object with connection details
        
    Returns:
        dict: Health status information
    """
    health_info = {
        'status': 'unknown',
        'message': '',
        'details': {},
        'api_version': None,
        'engine_version': None,
        'permissions': {
            'docker_access': False,
            'sudo_required': None
        }
    }
    
    # Connect to the server
    client = get_connection(
        hostname=server.hostname,
        username=server.username,
        port=server.ssh_port or 22,
        password=server.password,
        key_data=server.private_key if hasattr(server, 'private_key') else None,
        key_file=server.key_file_path if hasattr(server, 'key_file_path') else None
    )
    
    if not client:
        health_info['status'] = 'offline'
        health_info['message'] = 'Failed to establish SSH connection'
        return health_info
    
    # Test Docker permissions
    permission_test = test_docker_command_permissions(client, use_sudo=getattr(server, 'use_sudo', False))
    health_info['permissions']['docker_access'] = permission_test['direct_access_allowed']
    health_info['permissions']['sudo_required'] = permission_test['requires_sudo']
    
    # Store detected permission status on the server object if it has the attribute
    if hasattr(server, 'detected_sudo_required'):
        server.detected_sudo_required = permission_test['requires_sudo']
    
    # Use proper sudo setting based on test results
    use_sudo = getattr(server, 'use_sudo', False) or permission_test['requires_sudo']
    
    # Test Docker connectivity
    if not test_docker_connectivity(client, use_sudo=use_sudo):
        health_info['status'] = 'offline'
        health_info['message'] = 'Docker daemon not accessible'
        return health_info
    
    # Get Docker version
    version_info = get_docker_version(client, use_sudo=use_sudo)
    if not version_info:
        health_info['status'] = 'degraded'
        health_info['message'] = 'Docker is running but version info unavailable'
    else:
        # Extract API and Engine versions
        if 'Server' in version_info:
            if 'ApiVersion' in version_info['Server']:
                health_info['api_version'] = version_info['Server']['ApiVersion']
            elif 'Engine' in version_info['Server'] and 'ApiVersion' in version_info['Server']['Engine']:
                health_info['api_version'] = version_info['Server']['Engine']['ApiVersion']
                
            if 'Version' in version_info['Server']:
                health_info['engine_version'] = version_info['Server']['Version']
            elif 'Engine' in version_info['Server'] and 'Version' in version_info['Server']['Engine']:
                health_info['engine_version'] = version_info['Server']['Engine']['Version']
        
        # Check API v1.49 support
        api_version = health_info['api_version']
        if api_version and DockerApi149Support.is_api_149_supported(api_version):
            health_info['api_1_49_supported'] = True
            health_info['api_features'] = DockerApi149Support.get_api_features(api_version)
        else:
            health_info['api_1_49_supported'] = False
        
        # Get detailed info
        docker_info = get_docker_info(client, use_sudo=use_sudo)
        if docker_info:
            health_info['details'] = docker_info
            health_info['status'] = 'online'
            health_info['message'] = 'Docker server is healthy'
        else:
            health_info['status'] = 'degraded'
            health_info['message'] = 'Docker is running but detailed info unavailable'
    
    return health_info

def get_container_logs(client, container_id, tail=100, use_sudo=False, timestamp=False, since=None, until=None):
    """
    Get container logs with enhanced options
    
    Args:
        client (ParamikoSshClient): SSH client
        container_id (str): Container ID or name
        tail (int): Number of log lines to return
        use_sudo (bool): Whether to use sudo
        timestamp (bool): Include timestamps
        since (str): Show logs since timestamp (e.g. 2013-01-02T13:23:37Z)
        until (str): Show logs until timestamp (e.g. 2013-01-02T13:23:37Z)
        
    Returns:
        str: Container logs
    """
    cmd = f"container logs --tail={tail}"
    
    if timestamp:
        cmd += " --timestamps"
    
    if since:
        cmd += f" --since={since}"
    
    if until:
        cmd += f" --until={until}"
    
    cmd += f" {container_id}"
    
    success, result = run_docker_command(
        client, 
        cmd, 
        format_json=False, 
        use_sudo=use_sudo
    )
    
    if success:
        return result
    else:
        logger.error(f"Failed to get container logs: {result}")
        return None

def get_containers(client, all=True, use_sudo=False, api_version=None):
    """
    Get containers with API version awareness
    
    Args:
        client (ParamikoSshClient): SSH client
        all (bool): Include stopped containers
        use_sudo (bool): Whether to use sudo
        api_version (str): Docker API version
        
    Returns:
        list: Container information
    """
    cmd = "container ls"
    if all:
        cmd += " --all"
    
    # Use one-JSON-per-line format for easier parsing
    cmd += " --format '{{json .}}'"
    
    success, result = run_docker_command(
        client, 
        cmd, 
        format_json=False, 
        use_sudo=use_sudo
    )
    
    if not success:
        logger.error(f"Failed to get containers: {result}")
        return []
    
    # Parse one JSON object per line
    containers = []
    for line in result.strip().split('\n'):
        if line:
            try:
                container = json.loads(line)
                
                # Add platform info for API 1.49+
                if api_version and DockerApi149Support.is_api_149_supported(api_version):
                    # Get detailed info including platform
                    success, details = run_docker_command(
                        client,
                        f"container inspect {container['ID']}",
                        format_json=True,
                        use_sudo=use_sudo
                    )
                    
                    if success and isinstance(details, list) and len(details) > 0:
                        # Extract platform info
                        if 'Platform' in details[0]:
                            container['Platform'] = details[0]['Platform']
                        elif 'Config' in details[0] and 'Platform' in details[0]['Config']:
                            container['Platform'] = details[0]['Config']['Platform']
                
                containers.append(container)
            except json.JSONDecodeError:
                continue
    
    return containers

def get_api_version_info_html(server, client=None):
    """
    Generate HTML display for API version features
    
    Args:
        server: Docker server object
        client (ParamikoSshClient): Optional SSH client
        
    Returns:
        str: HTML formatted API version information
    """
    # Get a client if not provided
    if not client:
        client = get_connection(
            hostname=server.hostname,
            username=server.username,
            port=server.ssh_port or 22,
            password=server.password,
            key_data=server.private_key if hasattr(server, 'private_key') else None,
            key_file=server.key_file_path if hasattr(server, 'key_file_path') else None
        )
        
        if not client:
            return "<div class='alert alert-danger'>Failed to connect to server</div>"
    
    # Get server health to determine API version
    health = check_docker_server_health(server)
    api_version = health.get('api_version')
    
    if not api_version:
        return "<div class='alert alert-warning'>Could not determine Docker API version</div>"
    
    # Generate HTML display
    return DockerApi149Support.generate_api_version_html(api_version)

# Example usage
if __name__ == "__main__":
    # This is a simple test that would be run from command line
    # In practice, this module would be imported and used by Odoo models
    
    # Mock server object for testing
    class MockServer:
        def __init__(self):
            self.hostname = "example.com"
            self.username = "root"
            self.password = None
            self.private_key = "your_private_key_data"
            self.ssh_port = 22
            self.use_sudo = False
            self.detected_sudo_required = None
            
        def update_server_status(self, status, message):
            print(f"Server status updated: {status} - {message}")
    
    # Test the health check
    server = MockServer()
    health = check_docker_server_health(server)
    print(json.dumps(health, indent=2))