# Paramiko SSH Client

A standalone SSH client using the Paramiko library with improved output formatting options.

## Features

- **Clean Output Mode**: Return raw command output without additional formatting or HTML tags
- **Minimal Terminal Mode**: Use `TERM=dumb` to prevent ANSI escape sequences and color codes
- **PPK Key Support**: Automatically detects and converts PuTTY PPK format keys to PEM format
- **Interactive Mode**: Run in interactive shell mode for multiple commands
- **Command Mode**: Execute a single command and exit

This client is designed for both human use and system integration, where clean, machine-readable output is often required.

## Requirements

- Python 3.6+
- Paramiko library
- (Optional) PPK conversion support from `standalone_ppk_test.py`

## Usage

### Basic Connection

```bash
# Connect with password authentication
python paramiko_ssh_client.py --host server.example.com --user username --password yourpassword

# Connect with key authentication
python paramiko_ssh_client.py --host server.example.com --user username --key-file ~/.ssh/id_rsa
```

### Output Options

```bash
# Use clean output mode (no formatting)
python paramiko_ssh_client.py --host server.example.com --user username --key-file ~/.ssh/id_rsa --clean

# Disable minimal terminal mode (allow ANSI escape sequences)
python paramiko_ssh_client.py --host server.example.com --user username --key-file ~/.ssh/id_rsa --no-minimal-terminal
```

### Executing Commands

```bash
# Execute a single command
python paramiko_ssh_client.py --host server.example.com --user username --key-file ~/.ssh/id_rsa --command "ls -la"

# Execute a command and get clean output (for scripting)
python paramiko_ssh_client.py --host server.example.com --user username --key-file ~/.ssh/id_rsa --command "docker info --format '{{json .}}'" --clean
```

### Debug Mode

```bash
# Enable debug logging
python paramiko_ssh_client.py --host server.example.com --user username --key-file ~/.ssh/id_rsa --debug
```

## Interactive Mode

If you don't provide the `--command` argument, the client enters interactive mode, allowing you to type commands and see their output. Type `exit`, `quit`, or `logout` to disconnect.

## Integration with the PPK Converter

The client automatically integrates with the PPK key conversion functionality from `standalone_ppk_test.py` if available. This allows seamless handling of PuTTY PPK format keys without manual conversion.

## Use Cases

1. **Scripting and Automation**: The clean output mode is ideal for scripts that need to parse command output
2. **JSON Parsing**: Particularly useful for handling JSON output from tools like Docker, Kubernetes, etc.
3. **System Integration**: The minimal terminal mode prevents ANSI escape sequences that can break parsing
4. **Interactive Use**: The interactive mode provides a simple shell-like interface for running multiple commands

## Example Output Comparison

### Standard Output
```
[SUCCESS] Server status:
  CPU: 24%
  Memory: 1.2GB / 8GB
  Disk: 45GB / 100GB
```

### Clean Output
```
Server status:
  CPU: 24%
  Memory: 1.2GB / 8GB
  Disk: 45GB / 100GB
```

## Notes

- When using JSON formatted outputs from commands (like `docker info --format '{{json .}}'`), the clean output mode is especially useful to ensure the JSON is valid and parseable.
- The minimal terminal mode (`TERM=dumb`) helps prevent control characters that can break parsing, but some applications might provide less information in minimal mode.