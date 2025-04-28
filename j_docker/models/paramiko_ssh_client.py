import io
import os
import logging
import paramiko
import re
import socket
import time
from odoo import _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Compile ANSI color codes regex pattern once
ANSI_COLOR_PATTERN = re.compile(r'\x1b\[[0-9;]*m')

class ParamikoSSHClient:
    """SSH client based on Paramiko library for secure connections to remote servers.
    
    Provides a clean, reusable interface for making SSH connections and executing commands.
    Handles both password and key-based authentication.
    """
    
    def __init__(self, host, port=22, username=None, password=None, key=None, key_password=None,
                 timeout=10, keepalive=60, minimal_terminal=True):
        """Initialize SSH client connection parameters.
        
        Args:
            host (str): Hostname or IP address.
            port (int, optional): SSH port. Defaults to 22.
            username (str, optional): SSH username. Defaults to None.
            password (str, optional): SSH password for password auth. Defaults to None.
            key (str, optional): Private key content for key-based auth. Defaults to None.
            key_password (str, optional): Password for encrypted private key. Defaults to None.
            timeout (int, optional): Connection timeout in seconds. Defaults to 10.
            keepalive (int, optional): Keep-alive interval in seconds. Defaults to 60.
            minimal_terminal (bool, optional): Use minimal terminal to avoid ANSI codes. Defaults to True.
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.key = key
        self.key_password = key_password
        self.timeout = timeout
        self.keepalive = keepalive
        self.minimal_terminal = minimal_terminal
        self.client = None
    
    def connect(self):
        """Establish SSH connection to remote server.
        
        Returns:
            paramiko.SSHClient: Connected SSH client.
            
        Raises:
            UserError: If connection fails.
        """
        if self.client and self.client.get_transport() and self.client.get_transport().is_active():
            return self.client
            
        try:
            # Set up client
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            connect_params = {
                'hostname': self.host,
                'port': self.port,
                'username': self.username,
                'timeout': self.timeout,
                'allow_agent': False,
                'look_for_keys': False,
            }
            
            # Add authentication method
            if self.key:
                key_file = io.StringIO(self.key)
                pkey = None
                try:
                    # Try to parse as OpenSSH format first
                    pkey = paramiko.RSAKey.from_private_key(key_file, password=self.key_password)
                except paramiko.ssh_exception.SSHException:
                    # Reset file pointer and try different format
                    key_file.seek(0)
                    try:
                        # Try to parse as DSA key
                        pkey = paramiko.DSSKey.from_private_key(key_file, password=self.key_password)
                    except paramiko.ssh_exception.SSHException:
                        # Reset file pointer and try ECDSA format
                        key_file.seek(0)
                        try:
                            pkey = paramiko.ECDSAKey.from_private_key(key_file, password=self.key_password)
                        except paramiko.ssh_exception.SSHException:
                            # Reset and try Ed25519 format
                            key_file.seek(0)
                            try:
                                pkey = paramiko.Ed25519Key.from_private_key(key_file, password=self.key_password)
                            except:
                                raise UserError(_("Invalid private key format or incorrect password"))
                
                connect_params['pkey'] = pkey
            elif self.password:
                connect_params['password'] = self.password
            else:
                raise UserError(_("No authentication method provided. Please specify either password or private key."))
            
            # Try to connect with retries
            max_retries = 3
            retry_delay = 2
            for attempt in range(max_retries):
                try:
                    self.client.connect(**connect_params)
                    break
                except (socket.timeout, paramiko.ssh_exception.NoValidConnectionsError,
                        paramiko.ssh_exception.SSHException) as e:
                    if attempt < max_retries - 1:
                        _logger.warning(f"Connection attempt {attempt+1} failed: {str(e)}. Retrying in {retry_delay} seconds...")
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                    else:
                        raise UserError(_("Failed to connect to %s: %s") % (self.host, str(e)))
            
            # Set keep-alive
            if self.keepalive > 0:
                transport = self.client.get_transport()
                transport.set_keepalive(self.keepalive)
                
            return self.client
                
        except paramiko.AuthenticationException:
            raise UserError(_("Authentication failed for user %s on host %s") % (self.username, self.host))
        except paramiko.SSHException as e:
            raise UserError(_("SSH error: %s") % str(e))
        except Exception as e:
            raise UserError(_("Connection error: %s") % str(e))
    
    def execute_command(self, command, timeout=60):
        """Execute command on remote server.
        
        Args:
            command (str): Command to execute.
            timeout (int, optional): Command timeout in seconds. Defaults to 60.
            
        Returns:
            str: Command output.
            
        Raises:
            UserError: If command execution fails.
        """
        client = self.connect()
        
        try:
            # Set environment variables for minimal terminal if requested
            env = {}
            if self.minimal_terminal:
                env['TERM'] = 'dumb'
                env['NO_COLOR'] = '1'
                
            # Open channel and execute command
            transport = client.get_transport()
            channel = transport.open_session()
            
            # Set environment variables
            for key, value in env.items():
                channel.set_environment_variable(key, value)
                
            channel.settimeout(timeout)
            channel.set_combine_stderr(True)
            channel.exec_command(command)
            
            # Read output
            output_buffer = io.BytesIO()
            while True:
                data = channel.recv(1024)
                if not data:
                    break
                output_buffer.write(data)
                
            exit_status = channel.recv_exit_status()
            output = output_buffer.getvalue().decode('utf-8', errors='replace')
            
            # Remove ANSI color codes
            output = ANSI_COLOR_PATTERN.sub('', output)
            
            if exit_status != 0:
                _logger.warning(f"Command '{command}' exited with status {exit_status}")
                _logger.debug(f"Command output: {output}")
            
            return output
            
        except socket.timeout:
            raise UserError(_("Command execution timed out after %s seconds") % timeout)
        except paramiko.SSHException as e:
            raise UserError(_("SSH error during command execution: %s") % str(e))
        except Exception as e:
            raise UserError(_("Error executing command: %s") % str(e))
    
    def close(self):
        """Close SSH connection."""
        if self.client:
            self.client.close()
            self.client = None
            
    def __del__(self):
        """Destructor to ensure connection is closed."""
        self.close()