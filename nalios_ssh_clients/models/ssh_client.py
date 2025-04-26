# -*- coding: utf-8 -*-

import re
import paramiko
import base64 as b64
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from time import sleep
from io import StringIO
from ansi2html import Ansi2HTMLConverter
from paramiko import ssh_exception

from .ssh_utils import convert_private_key_if_needed

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

    name = fields.Char()
    host = fields.Char()
    port = fields.Integer(default=22, group_operator=False)
    user = fields.Char()
    password = fields.Char()
    private_key = fields.Binary()
    private_key_filename = fields.Char()
    private_key_password = fields.Char()
    ssh_category_id = fields.Many2one('ssh.client.category', 'Category')
    # Terminal options
    terminal_background = fields.Char(default='#000000')
    terminal_text_color = fields.Char(default='#FFFFFF')
    # Routines
    ssh_routine_ids = fields.One2many('ssh.client.routine', 'ssh_client_id', 'Routines')

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
                    
                    # Check if the key is in PPK format and convert it if needed
                    _logger.info("Checking if key needs conversion from PPK to PEM")
                    private_key_string = convert_private_key_if_needed(
                        private_key_string, 
                        passphrase=self.private_key_password
                    )
                    
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
        self.ensure_one()
        ssh_connection = self.get_ssh_connection()
        ssh_connection.send(command + "\n")
        sleep(0.5)
        while not ssh_connection.recv_ready():
            sleep(0.5)
        alldata = ssh_connection.recv(1024)
        while ssh_connection.recv_ready():
            sleep(0.5)
            alldata += ssh_connection.recv(1024)
        alldata = re.sub(b'^'+command.encode('utf-8'), b'', alldata)
        conv = Ansi2HTMLConverter()
        return conv.convert(alldata.replace(b'\x00', b'').decode('utf-8')).replace('<pre class="ansi2html-content">\n', '<pre class="ansi2html-content">')

    def get_client_name(self):
        self.ensure_one()
        return self.name

    def disconnect_client(self):
        self.ensure_one()
        if self.id in SSH_CONN_CACHE:
            SSH_CONN_CACHE[self.id].close()
            del SSH_CONN_CACHE[self.id]
        return True
