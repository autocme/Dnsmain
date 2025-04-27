import re
import json
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

# Import the SSH output cleaning function from the server module
from ..models.docker_server import clean_ssh_output

_logger = logging.getLogger(__name__)

class DockerCommandWizard(models.TransientModel):
    _name = 'docker.command.wizard'
    _description = 'Docker Command Execution Wizard'
    
    server_id = fields.Many2one('docker.server', string='Docker Server', 
                               required=True, ondelete='cascade')
    command = fields.Char(string='Docker Command', required=True,
                         help="Enter a Docker command to execute, e.g. 'docker ps -a' or 'docker info'")
    result = fields.Text(string='Command Result', readonly=True)
    is_executed = fields.Boolean(string='Command Executed', default=False)
    
    @api.onchange('server_id')
    def _onchange_server_id(self):
        """When server is changed, reset the result"""
        self.result = False
        self.is_executed = False
    
    def action_execute(self):
        """Execute the Docker command on the selected server"""
        self.ensure_one()
        
        if not self.command:
            raise UserError(_('Please enter a command to execute'))
            
        if not self.server_id:
            raise UserError(_('Please select a server to execute the command on'))
        
        # Get the SSH client from the server
        ssh_client = self.server_id.ssh_client_id
        if not ssh_client:
            raise UserError(_('Server has no SSH client configured'))
        
        try:
            # Check if the command already starts with 'docker'
            cmd = self.command
            if not cmd.strip().startswith('docker'):
                cmd = f"docker {cmd}"
            
            # Apply sudo if needed
            cmd = self.server_id._prepare_docker_command(cmd)
                
            # Execute the command
            result = ssh_client.exec_command(cmd)
            
            # Check if the response contains HTML, which may indicate a sudo password prompt
            if '<!DOCTYPE' in result or '<html' in result:
                if 'sudo' in result.lower() and ('password' in result.lower() or 'authentication' in result.lower()):
                    # This is likely a sudo password prompt
                    error_message = 'Command failed: sudo requires password. Configure sudo with NOPASSWD or set sudo_requires_password flag.'
                    _logger.error(error_message)
                    self.server_id._create_log_entry('error', error_message)
                    
                    # Auto-update the server config if needed
                    if not self.server_id.sudo_requires_password:
                        self.server_id.sudo_requires_password = True
                        
                    # Set a clear error result
                    cleaned_result = "ERROR: Sudo password prompt detected. The server requires password authentication for sudo.\n\n" + \
                                    "Solutions:\n" + \
                                    "1. Configure the server with 'NOPASSWD' in sudoers file\n" + \
                                    "2. Set 'Sudo Requires Password' to True in server settings\n" + \
                                    "3. Disable 'Use Sudo' if not needed"
                    
                    self.write({
                        'result': cleaned_result,
                        'is_executed': True,
                    })
                    
                    return {
                        'type': 'ir.actions.act_window',
                        'res_model': self._name,
                        'view_mode': 'form',
                        'res_id': self.id,
                        'target': 'new',
                        'context': self._context,
                    }
            
            # Clean the output to remove ANSI codes, HTML tags, etc.
            cleaned_result = clean_ssh_output(result)
            
            # Check if the clean_ssh_output function detected a sudo password issue
            if cleaned_result == '{"error": "sudo_requires_password"}':
                error_message = 'Command failed: sudo requires password authentication'
                _logger.error(error_message)
                
                # Auto-update the server config if needed
                if not self.server_id.sudo_requires_password:
                    self.server_id.sudo_requires_password = True
                
                # Set a clear error result
                cleaned_result = "ERROR: Sudo password prompt detected. The server requires password authentication for sudo.\n\n" + \
                                "Solutions:\n" + \
                                "1. Configure the server with 'NOPASSWD' in sudoers file\n" + \
                                "2. Set 'Sudo Requires Password' to True in server settings\n" + \
                                "3. Disable 'Use Sudo' if not needed"
            
            # For Docker info and similar commands that are expected to return JSON,
            # we might want to pretty-print the JSON for better readability
            elif cmd.strip().endswith('json .}}\'') or ' --format ' in cmd and ' json' in cmd:
                try:
                    # Try to parse as JSON and pretty-print
                    json_data = json.loads(cleaned_result)
                    cleaned_result = json.dumps(json_data, indent=4, sort_keys=True)
                except (json.JSONDecodeError, TypeError):
                    # If not valid JSON, use the cleaned result as is
                    pass
                    
            # Store the cleaned result and mark as executed
            self.write({
                'result': cleaned_result,
                'is_executed': True,
            })
            
            # Log the command execution
            self.server_id._create_log_entry('info', f'Command executed: {cmd}')
            
            # Return self to refresh the wizard view
            return {
                'type': 'ir.actions.act_window',
                'res_model': self._name,
                'view_mode': 'form',
                'res_id': self.id,
                'target': 'new',
                'context': self._context,
            }
            
        except Exception as e:
            self.server_id._create_log_entry('error', f'Command execution failed: {str(e)}')
            raise UserError(_(f'Command execution failed: {str(e)}'))