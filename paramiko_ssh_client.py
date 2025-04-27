#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Standalone SSH client using Paramiko with improved output options

This script demonstrates direct usage of Paramiko for SSH connections with:
1. Clean output option (no HTML formatting or colors)
2. Minimal terminal mode (TERM=dumb) option to prevent ANSI escape sequences
"""

import os
import sys
import time
import socket
import paramiko
import argparse
import re
import logging
import base64
from io import StringIO

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import the PPK to PEM conversion from our utility module
try:
    from ssh_key_utils import is_ppk_format, convert_ppk_to_pem
    ppk_support = True
except ImportError:
    logger.warning("PPK conversion module not found. PPK key format will not be supported.")
    ppk_support = False


class ParamikoSshClient:
    """
    SSH client using Paramiko with improved output formatting options
    """
    def __init__(self, hostname, username, port=22, 
                 password=None, key_file=None, key_data=None, key_password=None,
                 use_clean_output=False, force_minimal_terminal=True,
                 connect_timeout=10, command_timeout=60, retry_count=3, retry_delay=2):
        """
        Initialize SSH client with connection parameters and formatting options
        
        Args:
            hostname (str): SSH server hostname or IP
            username (str): SSH username
            port (int): SSH port (default: 22)
            password (str, optional): SSH password
            key_file (str, optional): Path to private key file
            key_data (str, optional): Private key as string data
            key_password (str, optional): Password for encrypted private key
            use_clean_output (bool): If True, return raw output without formatting
            force_minimal_terminal (bool): If True, use TERM=dumb to prevent ANSI codes
            connect_timeout (int): Connection timeout in seconds (default: 10)
            command_timeout (int): Command execution timeout in seconds (default: 60)
            retry_count (int): Number of connection retries (default: 3)
            retry_delay (int): Delay in seconds between retries (default: 2)
        """
        self.hostname = hostname
        self.username = username
        self.port = port
        
        self.password = password
        self.key_file = key_file
        self.key_data = key_data
        self.key_password = key_password
        
        # Output options
        self.use_clean_output = use_clean_output
        self.force_minimal_terminal = force_minimal_terminal
        
        # Connection and retry settings
        self.connect_timeout = connect_timeout
        self.command_timeout = command_timeout
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        
        # Connection objects
        self.ssh_client = None
        self.shell = None
        
        logger.info(f"Initialized SSH client for {username}@{hostname}:{port}")
        logger.info(f"Connection settings: timeout={connect_timeout}s, retries={retry_count}, retry_delay={retry_delay}s")
        logger.info(f"Output options: clean_output={use_clean_output}, minimal_terminal={force_minimal_terminal}")
        
    def load_key(self):
        """
        Load private key from file or string data
        
        Returns:
            paramiko.PKey: The private key object or None if not available
        """
        if not self.key_file and not self.key_data:
            return None
            
        try:
            key = None
            
            # If we have key data as string
            if self.key_data:
                logger.info("Loading private key from string data")
                
                # Check if it's in PPK format and convert if needed
                if ppk_support and is_ppk_format(self.key_data):
                    logger.info("Detected PPK format, converting to PEM")
                    self.key_data = convert_ppk_to_pem(self.key_data, self.key_password)
                    if not self.key_data:
                        logger.error("Failed to convert PPK key to PEM format")
                        return None
                
                # Create a file-like object from the key data
                key_file_obj = StringIO(self.key_data)
                
                # Try different key types
                for key_class in [paramiko.RSAKey, paramiko.Ed25519Key, paramiko.DSSKey, paramiko.ECDSAKey]:
                    key_file_obj.seek(0)  # Reset file position
                    try:
                        if self.key_password:
                            key = key_class.from_private_key(key_file_obj, self.key_password)
                        else:
                            key = key_class.from_private_key(key_file_obj)
                        logger.info(f"Successfully loaded key as {key_class.__name__}")
                        break
                    except Exception as e:
                        logger.debug(f"Failed to load key as {key_class.__name__}: {str(e)}")
                        continue
            
            # If we have a key file path
            elif self.key_file:
                logger.info(f"Loading private key from file: {self.key_file}")
                
                # Expand user home directory if needed (~/id_rsa)
                key_path = os.path.expanduser(self.key_file)
                
                # Check for existence
                if not os.path.exists(key_path):
                    logger.error(f"Key file not found: {key_path}")
                    return None
                
                # Read the file content to check if it's PPK format
                with open(key_path, 'r') as f:
                    key_content = f.read()
                
                # Check if it's in PPK format and convert if needed
                if ppk_support and is_ppk_format(key_content):
                    logger.info("Detected PPK format in key file, converting to PEM")
                    pem_content = convert_ppk_to_pem(key_content, self.key_password)
                    if pem_content:
                        # Create a file-like object from the converted key
                        key_file_obj = StringIO(pem_content)
                        
                        # Try different key types
                        for key_class in [paramiko.RSAKey, paramiko.Ed25519Key, paramiko.DSSKey, paramiko.ECDSAKey]:
                            key_file_obj.seek(0)  # Reset file position
                            try:
                                if self.key_password:
                                    key = key_class.from_private_key(key_file_obj, self.key_password)
                                else:
                                    key = key_class.from_private_key(key_file_obj)
                                logger.info(f"Successfully loaded converted PPK key as {key_class.__name__}")
                                break
                            except Exception as e:
                                logger.debug(f"Failed to load key as {key_class.__name__}: {str(e)}")
                                continue
                    else:
                        logger.error("Failed to convert PPK key to PEM format")
                else:
                    # Not PPK or conversion not available, try to load directly
                    # Try different key types
                    for key_class in [paramiko.RSAKey, paramiko.Ed25519Key, paramiko.DSSKey, paramiko.ECDSAKey]:
                        try:
                            if self.key_password:
                                key = key_class.from_private_key_file(key_path, self.key_password)
                            else:
                                key = key_class.from_private_key_file(key_path)
                            logger.info(f"Successfully loaded key as {key_class.__name__}")
                            break
                        except Exception as e:
                            logger.debug(f"Failed to load key as {key_class.__name__}: {str(e)}")
                            continue
            
            if not key:
                logger.error("Failed to load key in any supported format")
            
            return key
            
        except Exception as e:
            logger.error(f"Error loading private key: {str(e)}")
            import traceback
            logger.debug(traceback.format_exc())
            return None
    
    def connect(self):
        """
        Connect to the SSH server with retry capability
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        # Load private key if provided (do this once outside retry loop)
        key = self.load_key() if (self.key_file or self.key_data) else None
        
        # Initialize retry counter
        retry_count = 0
        last_error = None
        
        while retry_count <= self.retry_count:
            try:
                if retry_count > 0:
                    logger.info(f"Retrying connection (attempt {retry_count}/{self.retry_count})...")
                    time.sleep(self.retry_delay)  # Wait before retry
                
                # Create a new SSH client for each attempt
                if self.ssh_client:
                    try:
                        self.ssh_client.close()
                    except:
                        pass
                        
                self.ssh_client = paramiko.SSHClient()
                self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                
                # Connect to the server with timeout
                logger.info(f"Connecting to {self.hostname}:{self.port} as {self.username}")
                self.ssh_client.connect(
                    hostname=self.hostname,
                    port=self.port,
                    username=self.username,
                    password=self.password if not key else None,
                    pkey=key,
                    timeout=self.connect_timeout,
                    banner_timeout=self.connect_timeout,
                    auth_timeout=self.connect_timeout
                )
                
                # Get an interactive shell
                self.shell = self.ssh_client.invoke_shell(
                    width=132,  # Wider terminal to reduce line wrapping
                    height=50
                )
                time.sleep(0.5)  # Wait for shell to initialize
                
                # Receive the initial banner
                if self.shell.recv_ready():
                    banner = self.shell.recv(4096).decode('utf-8', errors='replace')
                    logger.debug(f"Received banner: {banner}")
                
                # Set terminal environment variable immediately if needed
                if self.force_minimal_terminal:
                    self.shell.send("export TERM=dumb\n".encode('utf-8'))
                    time.sleep(0.2)
                    # Clear any output from the TERM command
                    if self.shell.recv_ready():
                        self.shell.recv(4096)
                
                logger.info("Successfully connected to SSH server")
                return True
                
            except socket.timeout:
                last_error = "Connection timed out"
                logger.warning(f"Connection timed out (attempt {retry_count+1}/{self.retry_count+1})")
            except paramiko.ssh_exception.NoValidConnectionsError as e:
                last_error = str(e)
                logger.warning(f"No valid connections: {str(e)} (attempt {retry_count+1}/{self.retry_count+1})")
            except paramiko.ssh_exception.AuthenticationException as e:
                # Don't retry authentication failures - they won't resolve themselves
                logger.error(f"Authentication failed: {str(e)}")
                return False
            except paramiko.ssh_exception.SSHException as e:
                last_error = str(e)
                logger.warning(f"SSH error: {str(e)} (attempt {retry_count+1}/{self.retry_count+1})")
            except socket.error as e:
                last_error = str(e)
                logger.warning(f"Socket error: {str(e)} (attempt {retry_count+1}/{self.retry_count+1})")
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Connection error: {str(e)} (attempt {retry_count+1}/{self.retry_count+1})")
                import traceback
                logger.debug(traceback.format_exc())
            
            retry_count += 1
        
        # All retries failed
        logger.error(f"Failed to connect after {self.retry_count+1} attempts. Last error: {last_error}")
        return False
    
    def execute_command(self, command, retry_on_failure=True, timeout=None):
        """
        Execute a command on the SSH server with retry capability
        
        Args:
            command (str): Command to execute
            retry_on_failure (bool): Whether to retry on socket/SSH errors
            timeout (int): Command-specific timeout in seconds (overrides default)
            
        Returns:
            str: Command output
        """
        if not self.ssh_client or not self.shell:
            logger.error("Not connected. Call connect() first.")
            # Try to auto-reconnect
            if retry_on_failure and self.connect():
                logger.info("Auto-reconnected to server")
            else:
                return "ERROR: Not connected to SSH server"
        
        # Use command timeout or default
        cmd_timeout = timeout or self.command_timeout
        
        # Initialize retry counter
        retry_count = 0
        max_retries = self.retry_count if retry_on_failure else 0
        
        while retry_count <= max_retries:
            try:
                if retry_count > 0:
                    logger.info(f"Retrying command (attempt {retry_count}/{max_retries})...")
                    time.sleep(self.retry_delay)  # Wait before retry
                    
                    # Check if we need to reconnect
                    if not self.ssh_client or not self.shell:
                        if not self.connect():
                            logger.error("Failed to reconnect for command retry")
                            return "ERROR: Connection lost and reconnection failed"
                
                # Apply minimal terminal option if enabled
                if self.force_minimal_terminal:
                    modified_command = f"export TERM=dumb && {command}"
                else:
                    modified_command = command
                    
                logger.debug(f"Executing command: {modified_command}")
                
                # Send the command - ensure it's encoded to bytes
                self.shell.send((modified_command + "\n").encode('utf-8'))
                
                # Wait a moment for the command to start
                time.sleep(0.1)
                
                # Collect output with timeout
                output = b""
                start_time = time.time()
                last_receive_time = start_time
                
                # Wait for initial data with timeout
                initial_timeout = min(5, cmd_timeout / 2)  # At most 5 seconds or half the total timeout
                while not self.shell.recv_ready() and time.time() - start_time < initial_timeout:
                    time.sleep(0.1)
                
                # Read initial data if available
                if self.shell.recv_ready():
                    chunk = self.shell.recv(4096)
                    output += chunk
                    last_receive_time = time.time()
                else:
                    # In some cases, especially with Docker commands, the initial response might be delayed
                    # so we'll continue waiting for the total timeout
                    logger.warning(f"No initial response within {initial_timeout}s - continuing to wait")
                
                # Continue reading while data is available or we haven't reached timeout
                keep_reading = True
                while keep_reading and time.time() - start_time < cmd_timeout:
                    # Check if data is available
                    if self.shell.recv_ready():
                        chunk = self.shell.recv(8192)  # Larger buffer for faster reading
                        if not chunk:  # Connection closed
                            logger.warning("Connection closed while reading command output")
                            keep_reading = False
                        else:
                            output += chunk
                            last_receive_time = time.time()
                    else:
                        # No data available, wait a bit
                        time.sleep(0.1)
                        
                        # Check for end of command conditions:
                        # 1. We've waited 1-2 seconds after last data
                        # 2. Shell is showing a prompt (look for prompt indicators in output)
                        
                        # Time since last data received
                        idle_time = time.time() - last_receive_time
                        
                        # Check for prompt indicators in the last part of output
                        last_output = output[-50:].decode('utf-8', errors='replace') if output else ""
                        has_prompt = (
                            '$' in last_output.split('\n')[-1] or  # Bash
                            '#' in last_output.split('\n')[-1] or  # Root/sudo
                            '>' in last_output.split('\n')[-1]      # Some other shells
                        )
                        
                        # End conditions
                        if idle_time > 1.0 and (has_prompt or idle_time > 2.0):
                            keep_reading = False
                
                # Check if we timed out waiting for complete output
                if time.time() - start_time >= cmd_timeout:
                    logger.warning(f"Command execution timed out after {cmd_timeout}s")
                    output += b"\n[Command timed out - output may be incomplete]"
                
                # Decode the output with error handling
                try:
                    text_output = output.decode('utf-8', errors='replace')
                except Exception as e:
                    logger.error(f"Error decoding command output: {str(e)}")
                    text_output = output.decode('latin-1', errors='replace')  # Fallback encoding
                
                # Process and return the output
                return self._process_output(text_output, command)
                
            except socket.timeout:
                logger.warning(f"Command timed out (attempt {retry_count+1}/{max_retries+1})")
                if retry_count == max_retries:
                    return "ERROR: Command execution timed out"
            except (paramiko.ssh_exception.SSHException, socket.error) as e:
                logger.warning(f"SSH/Socket error during command: {str(e)} (attempt {retry_count+1}/{max_retries+1})")
                if retry_count == max_retries:
                    return f"ERROR: {str(e)}"
                
                # Try to reconnect for next attempt
                self.connect()
            except Exception as e:
                logger.error(f"Error executing command: {str(e)}")
                import traceback
                logger.debug(traceback.format_exc())
                
                if retry_count == max_retries:
                    return f"ERROR: {str(e)}"
            
            retry_count += 1
        
        # This should never be reached due to return in the loop, but just in case
        return "ERROR: Command execution failed after retries"
    
    def _process_output(self, output, command):
        """
        Process the command output according to the chosen options
        
        Args:
            output (str): Raw command output
            command (str): Original command
            
        Returns:
            str: Processed output
        """
        # Remove the echoed command from the beginning
        try:
            # Match the command at the beginning of the output
            # This handles cases where the shell adds the command to the output
            output_lines = output.split('\n')
            for i, line in enumerate(output_lines):
                if command in line:
                    # Skip this line and return the rest
                    output = '\n'.join(output_lines[i+1:])
                    break
        except Exception as e:
            logger.debug(f"Error removing command echo: {str(e)}")
        
        # Clean up the output
        output = output.replace('\r\n', '\n')  # Normalize line endings
        
        # If clean output is requested, return it as-is
        if self.use_clean_output:
            return output.strip()
        
        # Otherwise, add some basic formatting
        formatted_output = ""
        for line in output.split('\n'):
            # Highlight errors
            if "error" in line.lower() or "exception" in line.lower() or "failed" in line.lower():
                formatted_output += f"[ERROR] {line}\n"
            # Highlight success messages
            elif "success" in line.lower() or "completed" in line.lower():
                formatted_output += f"[SUCCESS] {line}\n"
            # Regular output
            else:
                formatted_output += line + "\n"
        
        return formatted_output.strip()
    
    def disconnect(self):
        """
        Close the SSH connection
        """
        if self.ssh_client:
            self.ssh_client.close()
            logger.info("SSH connection closed")


def parse_arguments():
    """
    Parse command line arguments
    
    Returns:
        argparse.Namespace: Parsed arguments
    """
    parser = argparse.ArgumentParser(description="Standalone SSH client using Paramiko")
    
    # Connection parameters
    parser.add_argument('--host', required=True, help="SSH server hostname or IP")
    parser.add_argument('--port', type=int, default=22, help="SSH port (default: 22)")
    parser.add_argument('--user', required=True, help="SSH username")
    parser.add_argument('--password', help="SSH password (prefer key auth when possible)")
    parser.add_argument('--key-file', help="Path to private key file")
    parser.add_argument('--key-password', help="Password for encrypted private key")
    
    # Output options
    parser.add_argument('--clean', action='store_true', help="Use clean output without formatting")
    parser.add_argument('--no-minimal-terminal', action='store_true', 
                        help="Disable minimal terminal mode (don't use TERM=dumb)")
    
    # Command execution
    parser.add_argument('--command', help="Command to execute (if not provided, enter interactive mode)")
    
    # Debug mode
    parser.add_argument('--debug', action='store_true', help="Enable debug logging")
    
    return parser.parse_args()


def interactive_mode(ssh_client):
    """
    Run in interactive mode, allowing the user to enter commands
    
    Args:
        ssh_client (ParamikoSshClient): Connected SSH client
    """
    print(f"\nConnected to {ssh_client.hostname} as {ssh_client.username}")
    print("Enter commands to execute. Type 'exit' or 'quit' to disconnect.\n")
    
    while True:
        try:
            command = input(f"{ssh_client.username}@{ssh_client.hostname}> ")
            
            if command.lower() in ['exit', 'quit', 'logout']:
                break
                
            if not command.strip():
                continue
                
            output = ssh_client.execute_command(command)
            print(output)
            print()
            
        except KeyboardInterrupt:
            print("\nInterrupted.")
            break
        except EOFError:
            print("\nEOF detected.")
            break


def main():
    """
    Main entry point
    """
    args = parse_arguments()
    
    # Set logging level
    if args.debug:
        logger.setLevel(logging.DEBUG)
        
    # Create SSH client
    client = ParamikoSshClient(
        hostname=args.host,
        port=args.port,
        username=args.user,
        password=args.password,
        key_file=args.key_file,
        key_password=args.key_password,
        use_clean_output=args.clean,
        force_minimal_terminal=not args.no_minimal_terminal
    )
    
    # Connect to the server
    if not client.connect():
        logger.error("Failed to connect.")
        return 1
        
    try:
        # Execute a command or enter interactive mode
        if args.command:
            output = client.execute_command(args.command)
            print(output)
        else:
            interactive_mode(client)
    finally:
        # Disconnect
        client.disconnect()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())