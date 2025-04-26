# -*- coding: utf-8 -*-

import re
import paramiko
import base64 as b64
import logging
import time

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from time import sleep
from io import StringIO
from ansi2html import Ansi2HTMLConverter
from paramiko import ssh_exception

from .ssh_utils import is_ppk_format, convert_ppk_to_pem

_logger = logging.getLogger(__name__)

SSH_CONN_CACHE = {}

class SshRoutineDebug(models.TransientModel):
    _name = 'ssh.routine.debug'
    _rec_name = 'debug'

    debug = fields.Html()

class SshClientRoutineCommand(models.Model):
    _name ='ssh.client.routine.command'
    _order = 'sequence'

    name = fields.Char('Command')
    routine_id = fields.Many2one('ssh.client.routine')
    sequence = fields.Integer()

class SshClientRoutine(models.Model):
    _name = 'ssh.client.routine'

    name = fields.Char()
    ssh_client_id = fields.Many2one('ssh.client')
    command_ids = fields.One2many('ssh.client.routine.command', 'routine_id', 'Commands')

    def run_routine(self):
        debug = ''
        self.ssh_client_id.get_ssh_connection()
        for command in self.command_ids:
            debug += self.ssh_client_id.exec_command(command.name)
        return {
            'type': 'ir.actions.act_window',
            'name': 'Routine Debug',
            'view_mode': 'form',
            'res_model': 'ssh.routine.debug',
            'context': {'default_debug': debug},
            'target': 'new',
        }
        

class SshClientCategory(models.Model):
    _name = 'ssh.client.category'

    name = fields.Char()

class SshClient(models.Model):
    _name = 'ssh.client'
    _description = 'SSH Client'

    name = fields.Char(string='Name', required=True)
    host = fields.Char(string='Host', required=True)
    port = fields.Integer(string='Port', default=22, group_operator=False, required=True)
    user = fields.Char(string='Username', required=True)
    password = fields.Char(string='Password')
    private_key = fields.Binary(string='Private Key')
    
    # Saved commands for this client
    saved_command_ids = fields.One2many('ssh.saved.command', 'ssh_client_id', string='Saved Commands')
    private_key_filename = fields.Char()
    private_key_password = fields.Char()
    auto_convert_ppk = fields.Boolean(
        string="Auto-convert PPK Keys", 
        default=False, 
        help="Enable to automatically convert PuTTY PPK format keys to PEM format. "
             "Disable to use the key as provided without conversion."
    )
    ssh_category_id = fields.Many2one('ssh.client.category', 'Category')
    # Terminal options
    terminal_background = fields.Char(default='#000000')
    terminal_text_color = fields.Char(default='#FFFFFF')
    # Routines
    ssh_routine_ids = fields.One2many('ssh.client.routine', 'ssh_client_id', 'Routines')
    
    # WebSSH Integration
    use_webssh = fields.Boolean(
        string="Use WebSSH Terminal", 
        default=True,
        help="Use the interactive WebSSH terminal interface which provides better experience with key handling, "
             "output formatting, and command-line features."
    )
    webssh_url = fields.Char(string="WebSSH URL", compute="_compute_webssh_url", store=False)
    
    # Helper properties for consistent access
    @property
    def hostname(self):
        return self.host
    
    @property
    def username(self):
        return self.user
        
    @property
    def auth_method(self):
        """Return the authentication method based on credentials provided"""
        if self.private_key:
            return 'key'
        elif self.password:
            return 'password'
        else:
            return 'unknown'

    @api.constrains('password', 'private_key')
    def _password_or_private_key(self):
        if self.password and self.private_key:
            raise UserError(_('You cannot have both password and private key. Please choose only one.'))

    def ssh_connect(self):
        return {
            'type': 'ir.actions.client',
            'tag': 'ssh_client_main_window',
            'target': 'fullscreen',
        }
        
    def webssh_connect(self):
        """Connect using the WebSSH interface"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/webssh/?client_id={self.id}',
            'target': 'self',
        }
        
    def _compute_webssh_url(self):
        """Compute the WebSSH URL for this client - implemented in webssh_integration.py"""
        for client in self:
            client.webssh_url = ""

    def get_colors(self):
        self.ensure_one()
        return {
            'background': self.terminal_background,
            'text': self.terminal_text_color,
        }

    def get_ssh_connection(self):
        self.ensure_one()
        ssh_connection = False
        if SSH_CONN_CACHE.get(self.id, False):
            ssh_connection = SSH_CONN_CACHE.get(self.id)
        if not ssh_connection:
            ssh_connection = paramiko.SSHClient()
            ssh_connection.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            if not self.password and self.private_key:
                try:
                    # Decode the binary private key to a string
                    _logger.info(f"Decoding private key for connection to {self.host}:{self.port}")
                    private_key_string = b64.decodebytes(self.private_key).decode('utf-8')
                    
                    # Log the first few characters of the key to help with debugging
                    # (don't log the entire key for security reasons)
                    first_line = private_key_string.split('\n')[0] if '\n' in private_key_string else private_key_string[:20]
                    _logger.info(f"Key starts with: {first_line}...")
                    
                    # Check if the key is in PPK format and convert it if auto-convert is enabled
                    if self.auto_convert_ppk and is_ppk_format(private_key_string):
                        _logger.info("Auto-convert PPK enabled: Converting PPK to PEM format")
                        converted_key = convert_ppk_to_pem(private_key_string, passphrase=self.private_key_password)
                        if converted_key:
                            _logger.info("PPK to PEM conversion successful")
                            private_key_string = converted_key
                        else:
                            _logger.warning("PPK to PEM conversion failed, using original key")
                    else:
                        if is_ppk_format(private_key_string):
                            _logger.info("Key appears to be in PPK format but auto-convert is disabled. Using as-is.")
                    
                    # Create a StringIO object to use with paramiko
                    private_key_fakefile = StringIO(private_key_string)
                    
                    # Try loading the key with different formats
                    private_key = None
                    errors = []
                    
                    # Try RSA key format first
                    try:
                        _logger.info("Trying to load key as RSA format")
                        if self.private_key_password:
                            private_key = paramiko.RSAKey.from_private_key(
                                private_key_fakefile, 
                                self.private_key_password
                            )
                        else:
                            private_key = paramiko.RSAKey.from_private_key(private_key_fakefile)
                        _logger.info("Successfully loaded key as RSA format")
                    except Exception as e:
                        private_key_fakefile.seek(0)
                        errors.append(f"RSA format error: {str(e)}")
                        _logger.warning(f"Failed to load key as RSA: {str(e)}")
                    
                    # If RSA failed, try Ed25519
                    if not private_key:
                        try:
                            _logger.info("Trying to load key as Ed25519 format")
                            if self.private_key_password:
                                private_key = paramiko.Ed25519Key.from_private_key(
                                    private_key_fakefile, 
                                    self.private_key_password
                                )
                            else:
                                private_key = paramiko.Ed25519Key.from_private_key(private_key_fakefile)
                            _logger.info("Successfully loaded key as Ed25519 format")
                        except Exception as e:
                            private_key_fakefile.seek(0)
                            errors.append(f"Ed25519 format error: {str(e)}")
                            _logger.warning(f"Failed to load key as Ed25519: {str(e)}")
                    
                    # If still failed, try DSS/DSA
                    if not private_key:
                        try:
                            _logger.info("Trying to load key as DSS/DSA format")
                            if self.private_key_password:
                                private_key = paramiko.DSSKey.from_private_key(
                                    private_key_fakefile, 
                                    self.private_key_password
                                )
                            else:
                                private_key = paramiko.DSSKey.from_private_key(private_key_fakefile)
                            _logger.info("Successfully loaded key as DSS/DSA format")
                        except Exception as e:
                            private_key_fakefile.seek(0)
                            errors.append(f"DSS format error: {str(e)}")
                            _logger.warning(f"Failed to load key as DSS/DSA: {str(e)}")
                    
                    # If still failed, try ECDSA
                    if not private_key:
                        try:
                            _logger.info("Trying to load key as ECDSA format")
                            if self.private_key_password:
                                private_key = paramiko.ECDSAKey.from_private_key(
                                    private_key_fakefile, 
                                    self.private_key_password
                                )
                            else:
                                private_key = paramiko.ECDSAKey.from_private_key(private_key_fakefile)
                            _logger.info("Successfully loaded key as ECDSA format")
                        except Exception as e:
                            private_key_fakefile.seek(0)
                            errors.append(f"ECDSA format error: {str(e)}")
                            _logger.warning(f"Failed to load key as ECDSA: {str(e)}")
                    
                    # If all key formats failed
                    if not private_key:
                        error_msg = "Could not load the private key in any supported format.\n"
                        error_msg += "Tried the following formats:\n- " + "\n- ".join(errors)
                        _logger.error(error_msg)
                        raise UserError(_("Could not load the private key. Please check the key format and password."))
                    
                    private_key_fakefile.close()
                    
                    # Connect with the key
                    _logger.info(f"Connecting to {self.host}:{self.port} with username {self.user} using private key")
                    ssh_connection.connect(
                        hostname=self.host,
                        port=self.port,
                        username=self.user,
                        pkey=private_key
                    )
                    _logger.info(f"Successfully connected to {self.host}:{self.port}")
                except Exception as e:
                    _logger.error(f"Error connecting with private key: {str(e)}")
                    import traceback
                    _logger.error(f"Connection traceback: {traceback.format_exc()}")
                    raise UserError(_("Failed to connect with private key: %s") % str(e))
            elif self.password and not self.private_key:
                try:
                    ssh_connection.connect(
                        hostname=self.host,
                        port=self.port,
                        username=self.user,
                        password=self.password,
                        allow_agent=False,
                    )
                except Exception as e:
                    _logger.error(f"Error connecting with password: {str(e)}")
                    raise UserError(_("Failed to connect with password: %s") % str(e))
            else:
                raise UserError(_("You must provide either a password or a private key."))
                
            SSH_CONN_CACHE[self.id] = ssh_connection.invoke_shell()
            sleep(0.5)
            while not SSH_CONN_CACHE.get(self.id).recv_ready():
                sleep(0.5)
            alldata = SSH_CONN_CACHE[self.id].recv(1024)
            while SSH_CONN_CACHE[self.id].recv_ready():
                alldata += SSH_CONN_CACHE[self.id].recv(1024)
            conv = Ansi2HTMLConverter()
            return conv.convert(alldata.replace(b'\x00', b'').decode('utf-8'))
        return ssh_connection

    def exec_command(self, command):
        """
        Execute a command on the SSH server with improved handling for interactive features
        and better output formatting for both AJAX and form-based approaches
        """
        self.ensure_one()
        
        try:
            ssh_connection = self.get_ssh_connection()
            
            # Send the command with a newline
            ssh_connection.send(command + "\n")
            
            # Initial wait for response
            sleep(0.5)
            
            # Wait a bit longer for slower servers
            timeout = 5  # 5 seconds max
            start_time = time.time()
            while not ssh_connection.recv_ready() and time.time() - start_time < timeout:
                sleep(0.2)
            
            # If we timed out without receiving data, return a message
            if not ssh_connection.recv_ready():
                return '<div class="terminal-warning">Command taking longer than expected. It may still be running...</div>'
            
            # Collect all the response data
            alldata = b''
            buffer_size = 4096  # Larger buffer for more efficient reads
            
            # Read initial data
            alldata += ssh_connection.recv(buffer_size)
            
            # Continue reading while there's data available
            while ssh_connection.recv_ready():
                sleep(0.1)  # Small delay between reads
                alldata += ssh_connection.recv(buffer_size)
            
            # Remove the command echo from the beginning of the response
            try:
                alldata = re.sub(b'^' + re.escape(command.encode('utf-8')), b'', alldata)
            except:
                # If regex fails, continue with unmodified data
                pass
                
            # Filter out control characters that may cause display issues
            alldata = alldata.replace(b'\x00', b'')
            
            # Handle special terminal codes for better output formatting
            formatted_data = self._format_terminal_output(alldata)
            
            # Convert ANSI escape sequences to HTML
            conv = Ansi2HTMLConverter(inline=True)
            html_output = conv.convert(formatted_data)
            
            # Cleanup the output for better display
            # Remove the outer pre tags from ansi2html if they exist
            html_output = html_output.replace('<pre class="ansi2html-content">', '')
            html_output = html_output.replace('</pre>', '')
            
            # Add syntax highlighting for common command outputs
            html_output = self._add_syntax_highlighting(html_output, command)
            
            # Wrap in a terminal-output div for styling
            return f'<div class="terminal-output">{html_output}</div>'
            
        except Exception as e:
            _logger.error(f"Command execution error: {str(e)}")
            return f'<div class="terminal-error">Error executing command: {str(e)}</div>'
        
    def _format_terminal_output(self, raw_data):
        """
        Format terminal output for better readability
        """
        try:
            # Decode the binary data
            text = raw_data.decode('utf-8', errors='replace')
            
            # Replace common problematic sequences
            text = text.replace('\r\n', '\n')  # Normalize line endings
            
            # Add proper spacing for command output sections
            if '|' in text and '-' in text and not '<table' in text:
                # Looks like a table output (ls -l, ps, etc.)
                text = self._format_table_output(text)
                
            return text
        except Exception as e:
            _logger.error(f"Error formatting terminal output: {str(e)}")
            return raw_data.decode('utf-8', errors='replace')
            
    def _format_table_output(self, text):
        """Format text that appears to be tabular for better display"""
        lines = text.split('\n')
        formatted_lines = []
        
        for line in lines:
            if '|' in line and len(line.split('|')) > 2:
                # This looks like a table row
                formatted_lines.append(f'<div class="terminal-table-row">{line}</div>')
            else:
                formatted_lines.append(line)
                
        return '\n'.join(formatted_lines)
    
    def _add_syntax_highlighting(self, html_output, command):
        """
        Add syntax highlighting for common command outputs
        """
        # Check if this is a common command that should get special formatting
        cmd_base = command.split()[0] if command.split() else ""
        
        if cmd_base in ['ls', 'dir']:
            # Highlight directories and files differently
            html_output = self._highlight_file_listing(html_output)
        elif cmd_base in ['docker', 'kubectl', 'aws']:
            # Add cloud tool highlighting
            html_output = self._highlight_cloud_tool_output(html_output, cmd_base)
        elif 'error' in html_output.lower() or 'exception' in html_output.lower():
            # Highlight errors
            html_output = html_output.replace(
                '<pre class="ansi2html-content">',
                '<pre class="ansi2html-content terminal-error-output">'
            )
            
        return html_output
        
    def _highlight_file_listing(self, html_output):
        """Add highlighting for file listings (ls command output)"""
        import re
        
        # First add the marker class
        html_output = html_output.replace(
            '<pre class="ansi2html-content">',
            '<pre class="ansi2html-content file-listing-output">'
        )
        
        # Look for common file listing patterns and add highlighting spans
        # This works both for standard HTML output and ANSI converted output
        
        # Function to wrap a matched pattern with a span class
        def highlight_match(match, css_class):
            return f'<span class="{css_class}">{match}</span>'
        
        # Apply regex patterns - these can handle both detailed and simple listings
        
        # 1. Directory names (either full "drwx..." entries or names ending with '/')
        html_output = re.sub(
            r'(d[-rwx]{9}.*?\s+\d+\s+\w+\s+\w+\s+\d+\s+\w+\s+\d+\s+[\d:]+\s+)(\S+)', 
            r'\1<span class="directory">\2</span>', 
            html_output
        )
        html_output = re.sub(r'(\s|^)(\S+/)(\s|$)', r'\1<span class="directory">\2</span>\3', html_output)
        
        # 2. Executable files (either full "-rwx..." entries or names ending with '*')
        html_output = re.sub(
            r'(-[-r][-w][-x].*?x.*?\s+\d+\s+\w+\s+\w+\s+\d+\s+\w+\s+\d+\s+[\d:]+\s+)(\S+)', 
            r'\1<span class="executable">\2</span>', 
            html_output
        )
        html_output = re.sub(r'(\s|^)(\S+\*)(\s|$)', r'\1<span class="executable">\2</span>\3', html_output)
        
        # 3. Symlinks (either full "l..." entries or 'name -> target' pattern)
        html_output = re.sub(
            r'(l[-rwx]{9}.*?\s+\d+\s+\w+\s+\w+\s+\d+\s+\w+\s+\d+\s+[\d:]+\s+)(\S+)(\s+->\s+)(\S+)', 
            r'\1<span class="symlink">\2\3\4</span>', 
            html_output
        )
        html_output = re.sub(r'(\S+)(\s+->\s+)(\S+)', r'<span class="symlink">\1\2\3</span>', html_output)
        
        # 4. Hidden files (starting with .)
        html_output = re.sub(r'(\s|^)(\.(?!\.\.)\S+)(\s|$)', r'\1<span class="hidden-file">\2</span>\3', html_output)
        
        # 5. Image files
        image_extensions = r'\.(?:jpg|jpeg|png|gif|svg|webp|bmp|ico|tiff)'
        html_output = re.sub(
            fr'(\s|^)(\S+{image_extensions})(\s|$)', 
            r'\1<span class="image-file">\2</span>\3', 
            html_output, 
            flags=re.IGNORECASE
        )
        
        # 6. Archive files
        archive_extensions = r'\.(?:zip|tar|gz|bz2|xz|rar|7z)'
        html_output = re.sub(
            fr'(\s|^)(\S+{archive_extensions})(\s|$)', 
            r'\1<span class="archive-file">\2</span>\3', 
            html_output, 
            flags=re.IGNORECASE
        )
        
        # 7. AWS-specific files/directories (for AWS integration)
        aws_patterns = [r'\.aws', r'aws-config', r'credentials', r'aws-cli']
        for pattern in aws_patterns:
            html_output = re.sub(
                fr'(\s|^)({pattern}\S*)(\s|$)', 
                r'\1<span class="aws-resource">\2</span>\3', 
                html_output, 
                flags=re.IGNORECASE
            )
        
        return html_output
        
    def _highlight_cloud_tool_output(self, html_output, tool):
        """Add highlighting for cloud tool outputs"""
        import re
        
        # First add the marker class
        html_output = html_output.replace(
            '<pre class="ansi2html-content">',
            f'<pre class="ansi2html-content cloud-tool-output {tool}-output">'
        )
        
        # Different highlighting based on which cloud tool is being used
        if tool == 'aws':
            # AWS resource identifiers (i-*, ami-*, vol-*, etc.)
            patterns = [
                # EC2 instances
                r'(i-[a-f0-9]{8,17})([^\w]|$)',
                # AMIs
                r'(ami-[a-f0-9]{8,17})([^\w]|$)',
                # EBS volumes
                r'(vol-[a-f0-9]{8,17})([^\w]|$)',
                # Security groups
                r'(sg-[a-f0-9]{8,17})([^\w]|$)',
                # S3 buckets
                r'(s3://[a-z0-9][-a-z0-9\.]*[a-z0-9])(/[^\\s]*)?([^\w]|$)',
                # ARNs
                r'(arn:aws:[a-z0-9\-]*:[a-z0-9\-]*:[0-9]{12}:[a-zA-Z0-9\-\*\/]+)([^\w]|$)',
            ]
            
            for pattern in patterns:
                html_output = re.sub(pattern, r'<span class="aws-resource">\1</span>\2', html_output)
            
            # AWS regions
            region_pattern = r'([^\w]|^)(us-east-1|us-east-2|us-west-1|us-west-2|eu-west-1|eu-west-2|eu-central-1|ap-northeast-1|ap-northeast-2|ap-southeast-1|ap-southeast-2|sa-east-1)([^\w]|$)'
            html_output = re.sub(region_pattern, r'\1<span class="aws-region">\2</span>\3', html_output)
            
            # AWS service names
            service_pattern = r'([^\w]|^)(ec2|s3|route53|cloudfront|rds|dynamodb|lambda|iam|vpc)([^\w-]|$)'
            html_output = re.sub(service_pattern, r'\1<span class="aws-service">\2</span>\3', html_output, flags=re.IGNORECASE)
            
            # AWS status indicators
            status_patterns = {
                'running': 'aws-status-running',
                'available': 'aws-status-running', 
                'active': 'aws-status-running',
                'stopped': 'aws-status-stopped',
                'stopping': 'aws-status-warning',
                'pending': 'aws-status-pending',
                'terminated': 'aws-status-terminated',
                'shutting-down': 'aws-status-terminated',
                'error': 'aws-status-error'
            }
            
            for status, css_class in status_patterns.items():
                pattern = fr'([^\w]|^)({status})([^\w-]|$)'
                html_output = re.sub(pattern, fr'\1<span class="{css_class}">\2</span>\3', html_output, flags=re.IGNORECASE)
                
        elif tool == 'docker':
            # Docker container IDs
            html_output = re.sub(r'([a-f0-9]{12})([^\w]|$)', r'<span class="docker-container">\1</span>\2', html_output)
            
            # Docker image names
            html_output = re.sub(r'([a-z0-9]+/[a-z0-9\-\_\.]+(?::[a-z0-9\.\-\_]+)?)', r'<span class="docker-image">\1</span>', html_output, flags=re.IGNORECASE)
            
            # Docker status indicators
            status_patterns = {
                'running': 'status-running',
                'created': 'status-created',
                'exited': 'status-exited',
                'up': 'status-up'
            }
            
            for status, css_class in status_patterns.items():
                pattern = fr'([^\w]|^)({status})([^\w-]|$)'
                html_output = re.sub(pattern, fr'\1<span class="{css_class}">\2</span>\3', html_output, flags=re.IGNORECASE)
        
        return html_output

    def test_connection(self):
        """
        Test the SSH connection by running a simple command
        """
        self.ensure_one()
        try:
            # Try to run a simple command like 'echo' to test the connection
            return self.exec_command('echo "Connection successful"')
        except Exception as e:
            _logger.error(f"SSH connection test failed: {str(e)}")
            return f'<div class="terminal-error">Connection test failed: {str(e)}</div>'

    def get_client_name(self):
        self.ensure_one()
        return self.name
        
    def create_temp_key_file(self):
        """
        Creates a temporary file with the private key for use with WebSSH
        
        Returns:
            str: Path to the temporary key file
        """
        self.ensure_one()
        
        if not self.private_key:
            return None
            
        try:
            # Decode the private key
            private_key_string = b64.decodebytes(self.private_key).decode('utf-8')
            
            # Check if the key is in PPK format and convert it if auto-convert is enabled
            if self.auto_convert_ppk and is_ppk_format(private_key_string):
                _logger.info("Auto-convert PPK enabled: Converting PPK to PEM format for temp file")
                converted_key = convert_ppk_to_pem(private_key_string, passphrase=self.private_key_password)
                if converted_key:
                    _logger.info("PPK to PEM conversion successful for temp file")
                    private_key_string = converted_key
                else:
                    _logger.warning("PPK to PEM conversion failed, using original key for temp file")
            
            # Create a temporary file
            import tempfile
            import os
            
            # Create a temporary file with the right permissions
            fd, path = tempfile.mkstemp()
            os.write(fd, private_key_string.encode())
            os.close(fd)
            
            # Set the right permissions (0600 = read/write only for owner)
            os.chmod(path, 0o600)
            
            return path
        except Exception as e:
            _logger.error(f"Error creating temporary key file: {e}")
            raise UserError(_(f"Failed to create temporary key file: {e}"))
            
    def get_webssh_connection(self):
        """
        Get connection details for WebSSH integration
        
        Returns:
            dict: Connection details for WebSSH
        """
        self.ensure_one()
        
        return {
            'host': self.host,
            'port': self.port,
            'username': self.user,
            'auth_method': self.auth_method,
            'client_id': self.id,
            'client_name': self.name
        }
    def get_connection_details(self):
        """Get connection details for display in the UI"""
        self.ensure_one()
        return {
            'id': self.id,
            'name': self.name,
            'host': self.host,
            'port': self.port,
            'user': self.user,
        }

    def disconnect_client(self):
        self.ensure_one()
        if self.id in SSH_CONN_CACHE:
            SSH_CONN_CACHE[self.id].close()
            del SSH_CONN_CACHE[self.id]
        return True
