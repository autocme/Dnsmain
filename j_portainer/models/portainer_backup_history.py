#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)

class PortainerBackupHistory(models.Model):
    _name = 'j_portainer.backup.history'
    _description = 'Portainer Backup History'
    _order = 'backup_date desc'
    _rec_name = 'display_name'

    server_id = fields.Many2one('j_portainer.server', string='Server', required=True, ondelete='cascade')
    schedule_id = fields.Many2one('j_portainer.backup.schedule', string='Backup Schedule',
                                 help="Link to schedule if this was an automated backup")
    backup_date = fields.Datetime('Backup Date', required=True, default=fields.Datetime.now)
    backup_file = fields.Many2one('ir.attachment', string='Backup File',
                                 help="The backup archive file")
    file_size = fields.Integer('File Size (Bytes)', help="Backup file size in bytes")
    file_size_mb = fields.Float('File Size (MB)', compute='_compute_file_size_mb', store=True)
    status = fields.Selection([
        ('in_progress', 'In Progress'),
        ('success', 'Success'),
        ('failed', 'Failed')
    ], string='Status', default='in_progress', required=True)
    error_message = fields.Text('Error Message', help="Error details if backup failed")
    manual_backup = fields.Boolean('Manual Backup', default=True,
                                  help="True if created manually, False if automated")
    display_name = fields.Char('Display Name', compute='_compute_display_name', store=True)
    
    # Backup file information
    filename = fields.Char('Filename', related='backup_file.name', readonly=True)
    download_url = fields.Char('Download URL', compute='_compute_download_url')
    
    @api.depends('file_size')
    def _compute_file_size_mb(self):
        """Convert file size from bytes to MB"""
        for record in self:
            if record.file_size:
                record.file_size_mb = record.file_size / (1024 * 1024)
            else:
                record.file_size_mb = 0.0
    
    @api.depends('server_id', 'backup_date', 'manual_backup')
    def _compute_display_name(self):
        """Compute display name for backup history"""
        for record in self:
            if record.server_id and record.backup_date:
                backup_type = "Manual" if record.manual_backup else "Scheduled"
                date_str = record.backup_date.strftime('%Y-%m-%d %H:%M')
                record.display_name = f"{record.server_id.name} - {backup_type} - {date_str}"
            else:
                record.display_name = "New Backup"
    
    @api.depends('backup_file')
    def _compute_download_url(self):
        """Compute download URL for backup file"""
        for record in self:
            if record.backup_file:
                record.download_url = f'/web/content/{record.backup_file.id}?download=true'
            else:
                record.download_url = False
    
    def action_download_backup(self):
        """Download backup file"""
        self.ensure_one()
        if not self.backup_file:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No File Available'),
                    'message': _('No backup file is available for download.'),
                    'sticky': False,
                    'type': 'warning',
                }
            }
        
        return {
            'type': 'ir.actions.act_url',
            'url': self.download_url,
            'target': 'self',
        }
    
    def action_delete_backup(self):
        """Delete backup history and associated file"""
        self.ensure_one()
        
        if self.backup_file:
            self.backup_file.unlink()
        
        backup_name = self.display_name
        self.unlink()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Backup Deleted'),
                'message': _('Backup "%s" has been deleted successfully.') % backup_name,
                'sticky': False,
                'type': 'success',
            }
        }
    
    def get_status_color(self):
        """Get color for status display"""
        self.ensure_one()
        status_colors = {
            'in_progress': 'warning',
            'success': 'success',
            'failed': 'danger'
        }
        return status_colors.get(self.status, 'secondary')
    
    @api.model
    def cleanup_old_backups(self, server_id, keep_count=10):
        """Clean up old backup files, keeping only the most recent ones
        
        Args:
            server_id (int): Server ID to clean up backups for
            keep_count (int): Number of recent backups to keep
        """
        try:
            # Get all successful backups for this server, ordered by date desc
            backups = self.search([
                ('server_id', '=', server_id),
                ('status', '=', 'success')
            ], order='backup_date desc')
            
            # Keep only the most recent backups
            old_backups = backups[keep_count:]
            
            if old_backups:
                _logger.info(f"Cleaning up {len(old_backups)} old backup files for server ID {server_id}")
                
                # Delete associated files first
                for backup in old_backups:
                    if backup.backup_file:
                        backup.backup_file.unlink()
                
                # Delete backup history records
                old_backups.unlink()
                
        except Exception as e:
            _logger.error(f"Error during backup cleanup for server ID {server_id}: {str(e)}")
    
    @api.model
    def get_backup_statistics(self, server_id):
        """Get backup statistics for a server
        
        Args:
            server_id (int): Server ID to get statistics for
            
        Returns:
            dict: Statistics including total backups, total size, last backup, etc.
        """
        backups = self.search([('server_id', '=', server_id)])
        successful_backups = backups.filtered(lambda b: b.status == 'success')
        
        stats = {
            'total_backups': len(backups),
            'successful_backups': len(successful_backups),
            'failed_backups': len(backups.filtered(lambda b: b.status == 'failed')),
            'total_size_mb': sum(successful_backups.mapped('file_size_mb')),
            'last_backup': max(backups.mapped('backup_date')) if backups else False,
            'last_successful_backup': max(successful_backups.mapped('backup_date')) if successful_backups else False,
        }
        
        return stats