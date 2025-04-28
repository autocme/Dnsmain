#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

# Update the import to use the new module
from ..models.docker_json_fix import clean_docker_output

_logger = logging.getLogger(__name__)

class DockerCommandWizard(models.TransientModel):
    _name = 'j_docker.command.wizard'
    _description = 'Docker Command Wizard'
    
    server_id = fields.Many2one('j_docker.docker_server', string='Server', required=True)
    command = fields.Char('Command', required=True, 
                         help="Enter the Docker command without the 'docker' prefix")
    result = fields.Text('Result', readonly=True)
    is_json = fields.Boolean('Parse as JSON', default=True)
    
    @api.model
    def default_get(self, fields_list):
        res = super(DockerCommandWizard, self).default_get(fields_list)
        
        # If called from a server, pre-fill the server_id
        active_model = self.env.context.get('active_model', '')
        active_id = self.env.context.get('active_id', False)
        
        if active_model == 'j_docker.docker_server' and active_id:
            res['server_id'] = active_id
            
        return res
    
    def execute_command(self):
        self.ensure_one()
        
        if not self.command:
            raise UserError(_("Please enter a command to execute"))
            
        try:
            # Execute the command on the server
            result = self.server_id.run_docker_command(self.command, as_json=self.is_json)
            
            # Format the result
            if isinstance(result, (dict, list)):
                import json
                self.result = json.dumps(result, indent=2)
            else:
                # Result is already a string, just use it
                self.result = result
                
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'j_docker.command.wizard',
                'res_id': self.id,
                'view_mode': 'form',
                'target': 'new',
            }
            
        except Exception as e:
            # If the error isn't user-friendly, make it more readable
            error_message = str(e)
            if "Traceback" in error_message:
                # Extract the last line of the traceback
                error_lines = error_message.split('\n')
                error_message = error_lines[-1] if error_lines else "Unknown error"
                
            raise UserError(f"Command execution failed: {error_message}")
    
    def save_command(self):
        """Save this command for later use"""
        self.ensure_one()
        
        # Create a saved command record
        self.env['j_docker.saved.command'].create({
            'name': f"Custom: {self.command[:30]}...",
            'command': self.command,
            'is_json': self.is_json,
            'description': f"Command executed on {self.server_id.name} at {fields.Datetime.now()}"
        })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Command Saved'),
                'message': _('The command has been saved for future use'),
                'sticky': False,
                'type': 'success',
            }
        }