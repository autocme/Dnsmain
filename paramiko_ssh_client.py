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
import paramiko
import argparse
import re
import logging
import base64
from io import StringIO

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import the PPK to PEM conversion if available
try:
    from standalone_ppk_test import is_ppk_format, convert_ppk_to_pem
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
                 use_clean_output=False, force_minimal_terminal=True):
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
        
        # Connection objects
        self.ssh_client = None
        self.shell = None
        
        logger.info(f"Initialized SSH client for {username}@{hostname}:{port}")
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
        Connect to the SSH server
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            # Create a new SSH client
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Load private key if provided
            key = self.load_key() if (self.key_file or self.key_data) else None
            
            # Connect to the server
            logger.info(f"Connecting to {self.hostname}:{self.port} as {self.username}")
            self.ssh_client.connect(
                hostname=self.hostname,
                port=self.port,
                username=self.username,
                password=self.password if not key else None,
                pkey=key
            )
            
            # Get an interactive shell
            self.shell = self.ssh_client.invoke_shell()
            time.sleep(0.5)  # Wait for shell to initialize
            
            # Receive the initial banner
            if self.shell.recv_ready():
                banner = self.shell.recv(4096).decode('utf-8', errors='replace')
                logger.debug(f"Received banner: {banner}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error connecting: {str(e)}")
            import traceback
            logger.debug(traceback.format_exc())
            return False
    
    def execute_command(self, command):
        """
        Execute a command on the SSH server
        
        Args:
            command (str): Command to execute
            
        Returns:
            str: Command output
        """
        if not self.shell:
            logger.error("Not connected. Call connect() first.")
            return "ERROR: Not connected"
        
        try:
            # Apply minimal terminal option if enabled
            if self.force_minimal_terminal:
                modified_command = f"export TERM=dumb && {command}"
            else:
                modified_command = command
                
            logger.debug(f"Executing command: {modified_command}")
            
            # Send the command
            self.shell.send(modified_command + "\n")
            
            # Wait a moment for the command to start
            time.sleep(0.5)
            
            # Collect output with timeout
            output = b""
            timeout = 10  # seconds
            start_time = time.time()
            
            # Wait for initial data
            while not self.shell.recv_ready() and time.time() - start_time < timeout:
                time.sleep(0.1)
            
            # Read initial data if available
            if self.shell.recv_ready():
                output += self.shell.recv(4096)
            else:
                logger.warning("Command timed out waiting for initial response")
                return "TIMEOUT: Command took too long to respond"
            
            # Continue reading while data is available
            while self.shell.recv_ready() or time.time() - start_time < timeout:
                if self.shell.recv_ready():
                    data = self.shell.recv(4096)
                    if not data:  # Connection closed
                        break
                    output += data
                    # Reset timeout when we receive data
                    start_time = time.time()
                else:
                    # No data available, wait a bit
                    time.sleep(0.1)
                    # Check if we've waited long enough since last data
                    if time.time() - start_time > 1.0:  # 1 second without new data
                        break
            
            # Decode the output
            text_output = output.decode('utf-8', errors='replace')
            
            # Process the output
            return self._process_output(text_output, command)
            
        except Exception as e:
            logger.error(f"Error executing command: {str(e)}")
            import traceback
            logger.debug(traceback.format_exc())
            return f"ERROR: {str(e)}"
    
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