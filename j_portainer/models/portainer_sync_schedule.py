# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)


class PortainerSyncSchedule(models.Model):
    _name = 'j_portainer.sync.schedule'
    _description = 'Portainer Sync Schedule Configuration'
    _order = 'sequence, server_id, name'
    
    # Core Fields
    name = fields.Char('Schedule Name', required=True, help="Descriptive name for this sync schedule")
    server_id = fields.Many2one('j_portainer.server', string='Server', required=True, ondelete='cascade',
                               help="Portainer server this schedule applies to")
    active = fields.Boolean('Active', default=True, help="Enable or disable this sync schedule")
    sequence = fields.Integer('Sequence', default=10, help="Order of execution for sync schedules")
    
    # Configuration Fields
    sync_days = fields.Integer('Sync Every (Days)', required=True, default=1,
                              help="Number of days between synchronizations (minimum 1)")
    sync_all_resources = fields.Boolean('Sync All Resources', default=False,
                                       help="If enabled, will sync all resource types ignoring individual selections")
    resource_type_ids = fields.Many2many('j_portainer.resource.type', string='Resource Types',
                                        help="Select which resource types to synchronize")
    
    # Tracking Fields
    last_sync = fields.Datetime('Last Synchronized', readonly=True,
                               help="Timestamp of the last successful synchronization")
    next_sync = fields.Datetime('Next Sync Due', compute='_compute_next_sync', store=True,
                               help="Calculated next synchronization time")
    
    # Status and Information Fields
    sync_status = fields.Selection([
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ], string='Status', default='pending', help="Current synchronization status")
    last_sync_result = fields.Text('Last Sync Result', readonly=True,
                                  help="Details of the last synchronization attempt")
    
    @api.depends('last_sync', 'sync_days')
    def _compute_next_sync(self):
        """Calculate when the next sync should occur"""
        for record in self:
            if record.last_sync and record.sync_days > 0:
                # Calculate next sync time based on last sync + interval
                next_sync_time = record.last_sync + timedelta(days=record.sync_days)
                record.next_sync = next_sync_time
            elif record.sync_days > 0:
                # If never synced, schedule for now
                record.next_sync = datetime.now()
            else:
                record.next_sync = False
    
    @api.constrains('sync_days')
    def _check_sync_days(self):
        """Validate that sync_days is at least 1"""
        for record in self:
            if record.sync_days < 1:
                raise ValidationError(_("Sync interval must be at least 1 day."))
    
    @api.constrains('sync_all_resources', 'resource_type_ids')
    def _check_resource_selection(self):
        """Validate that either sync_all_resources is True or resource_type_ids is selected"""
        for record in self:
            if not record.sync_all_resources and not record.resource_type_ids:
                raise ValidationError(_("Please either enable 'Sync All Resources' or select specific resource types."))
    
    @api.onchange('sync_all_resources')
    def _onchange_sync_all_resources(self):
        """Clear resource_type_ids when sync_all_resources is enabled"""
        if self.sync_all_resources:
            self.resource_type_ids = [(5, 0, 0)]  # Clear all many2many relations
    
    def get_resource_types_display(self):
        """Get formatted display of selected resource types"""
        self.ensure_one()
        if self.sync_all_resources:
            return "All Resources"
        elif self.resource_type_ids:
            return ", ".join(self.resource_type_ids.mapped('name'))
        return "None"
    
    def is_sync_due(self):
        """Check if this schedule is due for synchronization"""
        self.ensure_one()
        if not self.active:
            return False
        
        if not self.last_sync:
            # Never synced, so it's due
            _logger.info(f"Sync schedule '{self.name}' has never been synced - marking as due")
            return True
        
        if self.next_sync and datetime.now() >= self.next_sync:
            _logger.info(f"Sync schedule '{self.name}' is due for sync (next sync: {self.next_sync})")
            return True
        
        return False
    
    def execute_sync(self):
        """Execute the synchronization for this schedule"""
        self.ensure_one()
        _logger.info(f"Starting sync execution for schedule '{self.name}' on server '{self.server_id.name}'")
        
        if not self.server_id:
            _logger.error(f"No server configured for sync schedule '{self.name}'")
            return False
        
        # Update status to running
        self.write({
            'sync_status': 'running',
            'last_sync_result': f"Sync started at {datetime.now()}"
        })
        
        try:
            sync_results = []
            
            if self.sync_all_resources:
                # Sync all resources
                _logger.info(f"Syncing all resources for server '{self.server_id.name}'")
                result = self.server_id.sync_all_resources()
                sync_results.append("All Resources: " + str(result))
            else:
                # Sync specific resource types
                for resource_type in self.resource_type_ids:
                    _logger.info(f"Syncing {resource_type.name} for server '{self.server_id.name}'")
                    
                    # Get the sync method from the resource type
                    if hasattr(self.server_id, resource_type.sync_method):
                        sync_method = getattr(self.server_id, resource_type.sync_method)
                        result = sync_method()
                        sync_results.append(f"{resource_type.name}: {result}")
                    else:
                        _logger.warning(f"Server does not have sync method '{resource_type.sync_method}' for resource type '{resource_type.name}'")
                        sync_results.append(f"{resource_type.name}: Method not found")
            
            # Update successful completion
            self.write({
                'sync_status': 'completed',
                'last_sync': datetime.now(),
                'last_sync_result': "\n".join(sync_results)
            })
            
            _logger.info(f"Sync schedule '{self.name}' completed successfully")
            return True
            
        except Exception as e:
            error_msg = f"Sync failed: {str(e)}"
            _logger.error(f"Sync schedule '{self.name}' failed: {error_msg}")
            
            # Update failure status
            self.write({
                'sync_status': 'failed',
                'last_sync_result': error_msg
            })
            
            return False
    
    def name_get(self):
        """Custom name display"""
        result = []
        for record in self:
            name = f"{record.name} ({record.server_id.name}) - Every {record.sync_days} day(s)"
            result.append((record.id, name))
        return result
    
    @api.model
    def run_scheduled_syncs(self):
        """
        Main method called by the cron job to check and run due sync schedules
        This method runs every hour and checks all active sync schedules
        """
        _logger.info("Starting automated sync schedule runner")
        
        # Find all active sync schedules that are due for synchronization
        due_schedules = self.search([
            ('active', '=', True)
        ])
        
        executed_count = 0
        failed_count = 0
        
        for schedule in due_schedules:
            try:
                # Check if this schedule is due for sync
                if schedule.is_sync_due():
                    _logger.info(f"Executing scheduled sync: {schedule.name}")
                    
                    # Execute the sync
                    success = schedule.execute_sync()
                    
                    if success:
                        executed_count += 1
                        _logger.info(f"Successfully executed sync schedule: {schedule.name}")
                    else:
                        failed_count += 1
                        _logger.warning(f"Failed to execute sync schedule: {schedule.name}")
                        
                else:
                    # Not due yet, log when it will be due
                    if schedule.next_sync:
                        _logger.debug(f"Sync schedule '{schedule.name}' not due yet (next sync: {schedule.next_sync})")
                    
            except Exception as e:
                failed_count += 1
                _logger.error(f"Error executing sync schedule '{schedule.name}': {str(e)}")
                
                # Update the schedule with error status
                try:
                    schedule.write({
                        'sync_status': 'failed',
                        'last_sync_result': f"Cron execution failed: {str(e)}"
                    })
                except Exception as update_error:
                    _logger.error(f"Could not update schedule status: {str(update_error)}")
        
        total_schedules = len(due_schedules)
        _logger.info(f"Sync schedule runner completed: {total_schedules} schedules checked, "
                    f"{executed_count} executed, {failed_count} failed")
        
        return {
            'total_checked': total_schedules,
            'executed': executed_count,
            'failed': failed_count
        }