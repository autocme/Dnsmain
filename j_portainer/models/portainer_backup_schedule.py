#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)

class PortainerBackupSchedule(models.Model):
    _name = 'j_portainer.backup.schedule'
    _description = 'Portainer Backup Schedule'
    _rec_name = 'display_name'

    server_id = fields.Many2one('j_portainer.server', string='Server', required=True, ondelete='cascade')
    backup_password = fields.Char('Backup Password', required=True,
                                 help="Password used to encrypt automated backups")
    schedule_days = fields.Integer('Backup Every (Days)', default=1, required=True,
                                  help="Interval in days between automated backups")
    active = fields.Boolean('Enable Automated Backups', default=True,
                           help="Enable or disable automated backup scheduling")
    last_backup = fields.Datetime('Last Backup', readonly=True,
                                 help="Date and time of the last successful backup")
    next_backup = fields.Datetime('Next Backup', compute='_compute_next_backup', store=True,
                                 help="Calculated date and time for the next backup")
    display_name = fields.Char('Display Name', compute='_compute_display_name', store=True)
    
    # Statistics
    total_backups = fields.Integer('Total Backups', compute='_compute_backup_stats')
    backup_size_total = fields.Float('Total Backup Size (MB)', compute='_compute_backup_stats')
    
    # _sql_constraints = [
    #     ('unique_server_schedule', 'unique(server_id)', 'Each server can have only one backup schedule.'),
    #     ('positive_schedule_days', 'check(schedule_days > 0)', 'Schedule days must be positive.'),
    # ]
    
    @api.depends('server_id', 'schedule_days')
    def _compute_display_name(self):
        """Compute display name for the schedule"""
        for record in self:
            if record.server_id:
                if record.schedule_days == 1:
                    interval = "Daily"
                elif record.schedule_days == 7:
                    interval = "Weekly"
                else:
                    interval = f"Every {record.schedule_days} days"
                record.display_name = f"{record.server_id.name} - {interval}"
            else:
                record.display_name = "New Backup Schedule"
    
    @api.depends('last_backup', 'schedule_days', 'active')
    def _compute_next_backup(self):
        """Compute next backup date based on last backup and schedule"""
        for record in self:
            if record.active and record.last_backup and record.schedule_days:
                record.next_backup = record.last_backup + timedelta(days=record.schedule_days)
            elif record.active and not record.last_backup:
                # If no previous backup, schedule for now
                record.next_backup = datetime.now()
            else:
                record.next_backup = False
    
    def _compute_backup_stats(self):
        """Compute backup statistics"""
        for record in self:
            backup_history = self.env['j_portainer.backup.history'].search([
                ('server_id', '=', record.server_id.id),
                ('status', '=', 'success')
            ])
            record.total_backups = len(backup_history)
            record.backup_size_total = sum(backup_history.mapped('file_size_mb'))
    
    def is_backup_due(self):
        """Check if backup is due for this schedule"""
        self.ensure_one()
        if not self.active:
            return False
            
        if not self.last_backup:
            # No previous backup, so it's due
            return True
            
        next_backup_time = self.last_backup + timedelta(days=self.schedule_days)
        return datetime.now() >= next_backup_time
    
    def execute_backup(self):
        """Execute backup for this schedule"""
        self.ensure_one()
        
        if not self.active:
            _logger.info(f"Skipping backup for {self.server_id.name} - schedule is inactive")
            return False
            
        if not self.is_backup_due():
            _logger.info(f"Skipping backup for {self.server_id.name} - not due yet")
            return False
            
        try:
            _logger.info(f"Starting scheduled backup for server: {self.server_id.name}")
            
            # Create backup history record
            backup_history = self.env['j_portainer.backup.history'].create({
                'server_id': self.server_id.id,
                'schedule_id': self.id,
                'backup_date': datetime.now(),
                'status': 'in_progress',
                'manual_backup': False,
            })
            
            # Prepare backup payload
            backup_payload = {
                'password': self.backup_password
            }
            
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
                filename = f"portainer_backup_{self.server_id.name}_{timestamp}_scheduled.tar"
                
                # Create attachment
                attachment = self.env['ir.attachment'].create({
                    'name': filename,
                    'type': 'binary',
                    'datas': backup_content,
                    'res_model': 'j_portainer.backup.history',
                    'res_id': backup_history.id,
                    'mimetype': 'application/x-tar',
                    'description': f'Scheduled backup created on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
                })
                
                # Update backup history with success
                backup_history.write({
                    'backup_file': attachment.id,
                    'file_size': len(backup_content),
                    'file_size_mb': len(backup_content) / (1024 * 1024),
                    'status': 'success',
                })
                
                # Update schedule with last backup time
                self.write({
                    'last_backup': datetime.now()
                })
                
                _logger.info(f"Scheduled backup completed successfully: {filename} (Size: {len(backup_content)} bytes)")
                return True
                
            else:
                error_msg = f"HTTP {response.status_code}"
                try:
                    error_detail = response.json().get('message', response.text)
                    error_msg += f": {error_detail}"
                except:
                    error_msg += f": {response.text}"
                
                backup_history.write({
                    'status': 'failed',
                    'error_message': error_msg,
                })
                
                _logger.error(f"Scheduled backup failed for {self.server_id.name}: {error_msg}")
                return False
                
        except Exception as e:
            error_msg = str(e)
            _logger.error(f"Error during scheduled backup for {self.server_id.name}: {error_msg}")
            
            # Update backup history with error
            backup_history.write({
                'status': 'failed',
                'error_message': error_msg,
            })
            return False
    
    def action_execute_backup_now(self):
        """Manual execution of scheduled backup"""
        self.ensure_one()
        success = self.execute_backup()
        
        if success:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Backup Completed'),
                    'message': _('Scheduled backup executed successfully.'),
                    'sticky': False,
                    'type': 'success',
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Backup Failed'),
                    'message': _('Scheduled backup execution failed. Check the backup history for details.'),
                    'sticky': True,
                    'type': 'danger',
                }
            }