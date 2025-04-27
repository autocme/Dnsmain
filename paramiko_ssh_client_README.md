# Paramiko SSH Client with Enhanced Output Options

A standalone SSH client using Paramiko with improved output options specifically designed for machine-readable interaction with Docker and other remote services.

## Features

- **Clean Output Mode**: Returns raw command output without any formatting, perfect for JSON parsing
- **Minimal Terminal Mode**: Uses `TERM=dumb` to prevent ANSI escape sequences from corrupting output
- **Auto PPK Conversion**: Automatically detects and converts PuTTY's PPK key format to PEM
- **Support for Multiple Authentication Methods**:
  - Password authentication
  - Key-based authentication (RSA, DSA, ECDSA, Ed25519)
  - Private key data as string or file path
- **Smart Command Output Processing**:
  - Automatic removal of command echo from output
  - Timeout handling with sensible defaults
  - Line normalization and encoding handling

## Requirements

- Python 3.6+
- paramiko
- (Optional) Additional modules for PPK key support

## Installation

No installation is required. Simply download the script files and ensure you have paramiko installed:

```bash
pip install paramiko
```

## Usage

### As a Command-Line Tool

```bash
python paramiko_ssh_client.py --host <hostname> --port <port> --user <username> [options]
```

#### Options:

- `--host`: SSH server hostname or IP (required)
- `--port`: SSH port (default: 22)
- `--user`: SSH username (required)
- `--password`: SSH password (prefer key auth when possible)
- `--key-file`: Path to private key file
- `--key-password`: Password for encrypted private key
- `--clean`: Use clean output without formatting
- `--no-minimal-terminal`: Disable minimal terminal mode (don't use TERM=dumb)
- `--command`: Command to execute (if not provided, enter interactive mode)
- `--debug`: Enable debug logging

### As a Module in Other Scripts

```python
from paramiko_ssh_client import ParamikoSshClient

# Create SSH client with desired options
ssh_client = ParamikoSshClient(
    hostname="example.com",
    username="user",
    password="password",  # Or use key-based auth
    use_clean_output=True,  # For machine-readable output
    force_minimal_terminal=True  # To prevent ANSI escape sequences
)

# Connect to the server
if ssh_client.connect():
    # Execute commands
    output = ssh_client.execute_command("docker info --format '{{json .}}'")
    print(output)
    
    # Disconnect when done
    ssh_client.disconnect()
```

## Docker Integration Example

For a complete example of using this SSH client to interact with Docker, see the accompanying `docker_ssh_client_example.py` file.

The example demonstrates:

1. Getting Docker server information
2. Listing containers and images
3. Retrieving container statistics
4. Parsing the JSON output

```bash
python docker_ssh_client_example.py --host <hostname> --user <username> --action info
```

## Key Features for Docker Interaction

- Uses `--format '{{json .}}'` to get JSON output from Docker commands
- Cleanly handles JSON parsing by removing command echo and other non-JSON content
- Formats output in readable tables while preserving the raw data for programmatic use
- Handles common Docker commands like:
  - `docker info`
  - `docker ps -a`
  - `docker images`
  - `docker stats --no-stream`

## Troubleshooting

If you encounter JSON parsing errors, check that:

1. The clean output mode is enabled (`use_clean_output=True`)
2. The minimal terminal mode is enabled (`force_minimal_terminal=True`)
3. The command output actually contains valid JSON (some Docker commands may not support JSON format)

## License

This code is provided under an MIT license.