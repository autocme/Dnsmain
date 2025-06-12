#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)

class PortainerBackupWizard(models.TransientModel):
    _name = 'j_portainer.backup.wizard'
    _description = 'Portainer Backup Wizard'

    server_id = fields.Many2one('j_portainer.server', string='Server', required=True,
                               default=lambda self: self.env.context.get('active_id'))
    backup_password = fields.Char('Backup Password', required=True,
                                 help="Password to encrypt the backup archive")
    confirm_password = fields.Char('Confirm Password', required=True,
                                  help="Confirm the backup password")
    
    @api.constrains('backup_password', 'confirm_password')
    def _check_passwords_match(self):
        """Ensure passwords match"""
        for record in self:
            if record.backup_password != record.confirm_password:
                raise UserError(_("Passwords do not match. Please ensure both password fields are identical."))
    
    def action_create_backup(self):
        """Create backup from Portainer server"""
        self.ensure_one()
        
        if not self.server_id:
            raise UserError(_("No server selected for backup"))
            
        if not self.backup_password:
            raise UserError(_("Backup password is required"))
            
        try:
            # Prepare backup payload
            backup_payload = {
                'password': self.backup_password
            }
            
            _logger.info(f"Creating backup for Portainer server: {self.server_id.name}")
            
            # Make API request to create backup
            response = self.server_id._make_api_request(
                '/api/backup',
                method='POST',
                data=backup_payload
            )
            
            if response.status_code == 200:
                # Get backup content
                backup_content = response.content
                
                # Generate filename with timestamp
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"portainer_backup_{self.server_id.name}_{timestamp}.tar"
                
                # Encode backup content as base64 for Odoo attachment
                backup_base64 = base64.b64encode(backup_content)
                
                # Create attachment record
                attachment = self.env['ir.attachment'].create({
                    'name': filename,
                    'type': 'binary',
                    'datas': backup_base64,
                    'res_model': 'j_portainer.server',
                    'res_id': self.server_id.id,
                    'mimetype': 'application/x-tar',
                    'description': f'Portainer backup created on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
                })
                
                _logger.info(f"Backup created successfully: {filename} (Size: {len(backup_content)} bytes)")
                
                # Return download action
                return {
                    'type': 'ir.actions.act_url',
                    'url': f'/web/content/{attachment.id}?download=true',
                    'target': 'self',
                }
                
            elif response.status_code == 400:
                raise UserError(_("Invalid backup request. Please check your server configuration and try again."))
            elif response.status_code == 401:
                raise UserError(_("Authentication failed. Please check your API credentials."))
            elif response.status_code == 403:
                raise UserError(_("Access denied. Admin privileges required for backup operations."))
            else:
                error_msg = f"HTTP {response.status_code}"
                try:
                    error_detail = response.json().get('message', response.text)
                    error_msg += f": {error_detail}"
                except:
                    error_msg += f": {response.text}"
                raise UserError(_("Backup failed: %s") % error_msg)
                
        except Exception as e:
            _logger.error(f"Error creating backup: {str(e)}")
            if isinstance(e, UserError):
                raise
            else:
                raise UserError(_("Failed to create backup: %s") % str(e))
    
    def action_cancel(self):
        """Cancel backup wizard"""
        return {'type': 'ir.actions.act_window_close'}