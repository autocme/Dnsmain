#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import logging
import requests

_logger = logging.getLogger(__name__)

class PortainerRestoreWizard(models.TransientModel):
    _name = 'j_portainer.restore.wizard'
    _description = 'Portainer Restore Wizard'

    server_id = fields.Many2one('j_portainer.server', string='Server', required=True,
                               default=lambda self: self.env.context.get('active_id'))
    backup_file = fields.Binary('Backup File', required=True,
                               help="Select the Portainer backup archive (.tar file)")
    backup_filename = fields.Char('File Name')
    restore_password = fields.Char('Restore Password', required=True,
                                  help="Password used when creating the backup")
    confirm_restore = fields.Boolean('I understand the risks', 
                                   help="Confirm that you understand this will overwrite all current Portainer data")
    
    @api.onchange('backup_file')
    def _onchange_backup_file(self):
        """Validate backup file format"""
        if self.backup_file and self.backup_filename:
            if not self.backup_filename.lower().endswith(('.tar', '.tar.gz', '.tgz')):
                return {
                    'warning': {
                        'title': _('Invalid File Format'),
                        'message': _('Please select a valid Portainer backup file (.tar, .tar.gz, or .tgz)')
                    }
                }
    
    def action_restore_backup(self):
        """Restore Portainer from backup file"""
        self.ensure_one()
        
        if not self.server_id:
            raise UserError(_("No server selected for restore"))
            
        if not self.backup_file:
            raise UserError(_("Backup file is required"))
            
        if not self.restore_password:
            raise UserError(_("Restore password is required"))
            
        if not self.confirm_restore:
            raise UserError(_("You must confirm that you understand the risks before proceeding with the restore"))
            
        try:
            _logger.info(f"Starting restore for Portainer server: {self.server_id.name}")
            
            # Decode backup file from base64
            backup_content = base64.b64decode(self.backup_file)
            
            # Prepare multipart form data for restore
            files = {
                'file': (self.backup_filename or 'backup.tar', backup_content, 'application/x-tar')
            }
            
            data = {
                'password': self.restore_password
            }
            
            # Make API request to restore backup
            # Note: Using requests directly for multipart file upload
            url = f"{self.server_id.url.rstrip('/')}/api/restore"
            headers = {
                'X-API-Key': self.server_id.api_key
            }
            
            _logger.info(f"Uploading backup file for restore: {self.backup_filename} ({len(backup_content)} bytes)")
            
            response = requests.post(
                url,
                files=files,
                data=data,
                headers=headers,
                timeout=300  # 5 minutes timeout for restore operation
            )
            
            if response.status_code == 200:
                _logger.info(f"Restore completed successfully for server: {self.server_id.name}")
                
                # Clear any cached data in Odoo since Portainer data has changed
                self._clear_server_cache()
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Restore Completed'),
                        'message': _('Portainer has been successfully restored from backup. Please refresh your browser and re-sync all data.'),
                        'sticky': True,
                        'type': 'success',
                    }
                }
                
            elif response.status_code == 400:
                try:
                    error_detail = response.json().get('message', 'Invalid request')
                except:
                    error_detail = response.text
                raise UserError(_("Restore failed: %s") % error_detail)
            elif response.status_code == 401:
                raise UserError(_("Authentication failed. Please check your API credentials."))
            elif response.status_code == 500:
                try:
                    error_detail = response.json().get('message', 'Server error')
                except:
                    error_detail = 'Internal server error'
                raise UserError(_("Server error during restore: %s") % error_detail)
            else:
                error_msg = f"HTTP {response.status_code}"
                try:
                    error_detail = response.json().get('message', response.text)
                    error_msg += f": {error_detail}"
                except:
                    error_msg += f": {response.text}"
                raise UserError(_("Restore failed: %s") % error_msg)
                
        except requests.exceptions.Timeout:
            raise UserError(_("Restore operation timed out. Please check the Portainer server status manually."))
        except requests.exceptions.ConnectionError:
            raise UserError(_("Could not connect to Portainer server. Please check the server URL and network connectivity."))
        except Exception as e:
            _logger.error(f"Error during restore: {str(e)}")
            if isinstance(e, UserError):
                raise
            else:
                raise UserError(_("Failed to restore backup: %s") % str(e))
    
    def _clear_server_cache(self):
        """Clear all cached Portainer data for this server"""
        try:
            # Mark all environments for re-sync
            environments = self.env['j_portainer.environment'].search([
                ('server_id', '=', self.server_id.id)
            ])
            environments.write({'last_sync': False})
            
            # Optionally clear all synced data (uncomment if needed)
            # This would remove all containers, images, etc. from Odoo
            # forcing a complete re-sync after restore
            
            # self.env['j_portainer.container'].search([
            #     ('server_id', '=', self.server_id.id)
            # ]).unlink()
            # 
            # self.env['j_portainer.image'].search([
            #     ('server_id', '=', self.server_id.id)
            # ]).unlink()
            # 
            # self.env['j_portainer.volume'].search([
            #     ('server_id', '=', self.server_id.id)
            # ]).unlink()
            # 
            # self.env['j_portainer.stack'].search([
            #     ('server_id', '=', self.server_id.id)
            # ]).unlink()
            
            _logger.info(f"Cleared cache for server: {self.server_id.name}")
            
        except Exception as e:
            _logger.warning(f"Could not clear server cache: {str(e)}")
