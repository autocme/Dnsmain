# Enhanced Docker and SSH Connectivity

This package provides robust connectivity solutions for Docker and SSH connections, designed to handle network issues, timeouts, and provide better error recovery.

## Features

### SSH Client Enhancements
- **Connection Retries**: Automatically retry failed connections with configurable parameters
- **Improved Timeout Handling**: Better timeout management for connections and commands
- **Error Detection**: Intelligent error detection with custom handling for different error types
- **Output Processing**: Clean command output to remove ANSI codes and command echo
- **Terminal Mode Control**: Force minimal terminal mode to prevent ANSI codes
- **PPK Key Support**: Automatically convert PuTTY PPK keys to OpenSSH format

### Docker Connectivity
- **Connection Pooling**: Reuse SSH connections for better performance
- **Command Validation**: Ensure Docker commands are executed correctly
- **JSON Parsing**: Robust JSON extraction from command output
- **Error Recovery**: Automatic recovery from temporary failures
- **Health Monitoring**: Comprehensive Docker server health checks

## Components

### 1. Enhanced SSH Client (`paramiko_ssh_client.py`)
A robust SSH client built on Paramiko with improved error handling, retries, and output formatting.

```python
client = ParamikoSshClient(
    hostname="example.com",
    username="user",
    port=22,
    password="password",  # or use key authentication
    connect_timeout=10,
    command_timeout=60,
    retry_count=3,
    retry_delay=2
)

if client.connect():
    output = client.execute_command("your_command")
    print(output)
```

### 2. Docker Output Validator (`docker_output_validator.py`)
Utilities for validating and cleaning Docker command output, especially when received through SSH.

```python
from docker_output_validator import clean_docker_output, extract_json_from_output

# Clean Docker output to remove ANSI codes and command echo
clean_output = clean_docker_output(raw_output, "docker info")

# Extract JSON from potentially mixed content
json_data, error = extract_json_from_output(output)
if json_data:
    print(f"Container count: {json_data.get('Containers', 0)}")
```

### 3. Docker Connectivity (`docker_connectivity.py`)
High-level Docker connectivity with error handling, connection pooling, and retry capability.

```python
from docker_connectivity import get_connection, run_docker_command

client = get_connection(hostname="example.com", username="user")
if client:
    success, result = run_docker_command(client, "container ls", format_json=False)
    if success:
        print(result)
```

### 4. Docker Server Integration (`docker_server_integration.py`)
Example implementation showing how to integrate the Docker connectivity module with the Odoo Docker server model.

## Integration Guide

To integrate these enhancements into your Odoo module:

1. Copy the enhanced SSH client, Docker output validator, and Docker connectivity modules to your Odoo module

2. Update your Docker server model to use the `with_docker_connection` decorator for Docker operations:

```python
@with_docker_connection(max_retries=2)
def get_containers(self, client):
    success, result = run_docker_command(
        client, 
        "container ls --all --format '{{json .}}'", 
        format_json=False,
        use_sudo=self.use_sudo
    )
    
    if not success:
        raise UserError(f"Failed to get containers: {result}")
    
    # Process the result
    return containers
```

3. Use the `check_docker_server_health` function to implement comprehensive health checks:

```python
def check_health(self):
    health = check_docker_server_health(self)
    # Update server status based on health information
    self.status = health['status']
    self.status_message = health['message']
    return health['status'] == 'online'
```

## Testing

The `docker_connectivity_test.py` script provides comprehensive tests for all connectivity features:

```bash
python docker_connectivity_test.py --hostname example.com --username user --password pass --all
```

Available test options:
- `--connection`: Test basic connectivity
- `--pool`: Test connection pooling
- `--commands`: Test Docker commands
- `--health`: Test health check
- `--errors`: Test error handling

## Troubleshooting

### Connection Issues
- Verify SSH credentials and connectivity
- Check if Docker daemon is running on the remote server
- Ensure proper sudo permissions for Docker commands if needed

### Command Failures
- Check if command is supported by the installed Docker version
- Verify proper command formatting
- Check if timeout values are appropriate for the command

### JSON Parsing Errors
- Inspect the raw command output for unexpected content
- Check for warning messages or error output mixed with JSON data
- Ensure the command supports JSON formatting