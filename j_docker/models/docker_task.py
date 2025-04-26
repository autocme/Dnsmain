import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

class DockerTask(models.Model):
    _name = 'docker.task'
    _description = 'Docker Task'
    _order = 'sequence, id'
    _inherit = ['safe.read.mixin']
    # Commenting out mail inheritance until mail module is properly loaded
    # _inherit = ['mail.thread', 'mail.activity.mixin', 'safe.read.mixin']

    name = fields.Char(string='Name', required=True,
                     help="Name of the Docker task")
    
    server_id = fields.Many2one('docker.server', string='Server', required=True,
                              ondelete='cascade',
                              help="Server where this task will run")
    
    active = fields.Boolean(default=True)
    sequence = fields.Integer(string='Sequence', default=10, 
                            help="Order tasks in the scheduled list")
    
    # Task configuration
    task_type = fields.Selection([
        ('docker_command', 'Docker Command'),
        ('system_command', 'System Command'),
        ('container_action', 'Container Action'),
        ('image_action', 'Image Action'),
        ('network_action', 'Network Action'),
        ('volume_action', 'Volume Action'),
        ('prune_action', 'Prune Action')
    ], string='Task Type', required=True, default='docker_command')
    
    command = fields.Text(string='Command', 
                        help="Command to execute on the server")
    
    description = fields.Text(string='Description', 
                            help="Detailed description of what this task does")
    
    # Target objects for specific actions
    container_id = fields.Many2one('docker.container', string='Container',
                                 domain="[('server_id', '=', server_id)]")
    
    image_id = fields.Many2one('docker.image', string='Image',
                             domain="[('server_id', '=', server_id)]")
    
    network_id = fields.Many2one('docker.network', string='Network',
                               domain="[('server_id', '=', server_id)]")
    
    volume_id = fields.Many2one('docker.volume', string='Volume',
                              domain="[('server_id', '=', server_id)]")
    
    # Execution settings
    schedule_type = fields.Selection([
        ('manual', 'Manual Only'),
        ('cron', 'Scheduled'),
        ('event', 'On Event')
    ], string='Schedule Type', required=True, default='manual')
    
    cron_id = fields.Many2one('ir.cron', string='Scheduled Job',
                            help="Scheduled job for this task")
    
    cron_expr = fields.Char(string='Cron Expression',
                          help="Cron expression for scheduling (e.g. * * * * *)")
    
    event_trigger = fields.Selection([
        ('server_start', 'Server Start'),
        ('server_stop', 'Server Stop'),
        ('container_start', 'Container Start'),
        ('container_stop', 'Container Stop'),
        ('container_exit', 'Container Exit'),
        ('image_create', 'Image Created'),
        ('image_delete', 'Image Deleted')
    ], string='Event Trigger')
    
    # Execution control
    timeout = fields.Integer(string='Timeout (seconds)', default=60,
                           help="Maximum time in seconds the task is allowed to run")
    
    fail_action = fields.Selection([
        ('continue', 'Continue Execution'),
        ('stop', 'Stop Execution'),
        ('retry', 'Retry')
    ], string='On Failure', default='stop',
       help="What to do if the task fails")
    
    retry_count = fields.Integer(string='Retry Count', default=3,
                               help="Number of times to retry on failure")
    
    retry_delay = fields.Integer(string='Retry Delay (seconds)', default=60,
                               help="Delay between retries in seconds")
    
    # Execution statistics
    last_run = fields.Datetime(string='Last Run', readonly=True)
    next_run = fields.Datetime(string='Next Run', readonly=True)
    last_duration = fields.Float(string='Last Duration (seconds)', readonly=True)
    
    success_count = fields.Integer(string='Success Count', default=0, readonly=True)
    failure_count = fields.Integer(string='Failure Count', default=0, readonly=True)
    
    last_status = fields.Selection([
        ('none', 'Not Run'),
        ('success', 'Success'),
        ('failure', 'Failure'),
        ('running', 'Running')
    ], string='Last Status', default='none', readonly=True)
    
    last_output = fields.Text(string='Last Output', readonly=True)
    
    # Related logs
    log_ids = fields.One2many('docker.logs', 'task_id', string='Logs')
    
    # -------------------------------------------------------------------------
    # Compute and onchange methods
    # -------------------------------------------------------------------------
    @api.onchange('task_type')
    def _onchange_task_type(self):
        """Set default command based on task type"""
        if self.task_type == 'docker_command':
            self.command = 'docker '
        elif self.task_type == 'system_command':
            self.command = ''
        elif self.task_type == 'container_action':
            self.command = 'docker ps -a'
        elif self.task_type == 'image_action':
            self.command = 'docker images'
        elif self.task_type == 'network_action':
            self.command = 'docker network ls'
        elif self.task_type == 'volume_action':
            self.command = 'docker volume ls'
        elif self.task_type == 'prune_action':
            self.command = 'docker system prune -f'
    
    @api.onchange('container_id')
    def _onchange_container_id(self):
        """Update command when container is selected"""
        if self.task_type == 'container_action' and self.container_id:
            self.command = f'docker restart {self.container_id.docker_id}'
    
    @api.onchange('image_id')
    def _onchange_image_id(self):
        """Update command when image is selected"""
        if self.task_type == 'image_action' and self.image_id:
            self.command = f'docker pull {self.image_id.name}'
    
    @api.onchange('schedule_type')
    def _onchange_schedule_type(self):
        """Clear irrelevant fields based on schedule type"""
        if self.schedule_type == 'manual':
            self.cron_expr = False
            self.event_trigger = False
        elif self.schedule_type == 'cron':
            self.event_trigger = False
        elif self.schedule_type == 'event':
            self.cron_expr = False
    
    # -------------------------------------------------------------------------
    # CRUD methods
    # -------------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        records = super(DockerTask, self).create(vals_list)
        for record in records:
            if record.schedule_type == 'cron' and record.cron_expr:
                record._create_cron_job()
        return records
    
    def write(self, vals):
        result = super(DockerTask, self).write(vals)
        
        # Update cron job if needed
        if 'schedule_type' in vals or 'cron_expr' in vals or 'active' in vals:
            for task in self:
                if task.schedule_type == 'cron' and task.cron_expr:
                    task._create_cron_job()
                elif task.cron_id:
                    # Delete cron job if not scheduled anymore
                    task.cron_id.unlink()
                    task.cron_id = False
        
        return result
    
    def unlink(self):
        # Delete associated cron jobs
        for task in self:
            if task.cron_id:
                task.cron_id.unlink()
        
        return super(DockerTask, self).unlink()
    
    # -------------------------------------------------------------------------
    # Action methods
    # -------------------------------------------------------------------------
    def action_run_task(self):
        """Run the task manually"""
        self.ensure_one()
        result = self._execute_task()
        
        if result.get('success'):
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Task Executed'),
                    'message': _('Task %s executed successfully') % self.name,
                    'type': 'success',
                    'sticky': False,
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Task Failed'),
                    'message': result.get('error', _('Unknown error')),
                    'type': 'warning',
                    'sticky': False,
                }
            }
    
    def action_view_output(self):
        """View task output"""
        self.ensure_one()
        
        return {
            'name': _('Task Output'),
            'type': 'ir.actions.act_window',
            'res_model': 'docker.task.output.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_task_id': self.id,
                'default_output': self.last_output or _('No output yet')
            },
        }
    
    def action_view_logs(self):
        """View task logs"""
        self.ensure_one()
        
        return {
            'name': _('Task Logs'),
            'type': 'ir.actions.act_window',
            'res_model': 'docker.logs',
            'view_mode': 'tree,form',
            'domain': [('task_id', '=', self.id)],
            'context': {'default_task_id': self.id},
        }
    
    def action_schedule_task(self):
        """Open wizard to schedule the task"""
        self.ensure_one()
        
        return {
            'name': _('Schedule Task'),
            'type': 'ir.actions.act_window',
            'res_model': 'docker.schedule.task.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_task_id': self.id},
        }
    
    # -------------------------------------------------------------------------
    # Helper methods for task execution
    # -------------------------------------------------------------------------
    def _execute_task(self):
        """Execute the task"""
        self.ensure_one()
        
        if not self.active:
            return {'success': False, 'error': _('Cannot run inactive task')}
        
        if not self.server_id or not self.server_id.ssh_client_id:
            return {'success': False, 'error': _('Server SSH client not configured')}
        
        try:
            # Update task status
            self.last_status = 'running'
            start_time = fields.Datetime.now()
            
            # Get the final command to execute based on task type
            command = self._get_final_command()
            
            if not command:
                raise UserError(_('No command to execute'))
            
            # Execute the command on the server
            ssh_client = self.server_id.ssh_client_id
            result = ssh_client.exec_command(command)
            
            # Update task statistics
            end_time = fields.Datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            self.write({
                'last_run': start_time,
                'last_duration': duration,
                'last_output': result,
                'last_status': 'success',
                'success_count': self.success_count + 1
            })
            
            # Log the execution
            self._create_log_entry('info', f'Task executed successfully in {duration:.2f}s')
            
            return {'success': True, 'output': result}
            
        except Exception as e:
            # Update task statistics for failure
            self.write({
                'last_run': fields.Datetime.now(),
                'last_status': 'failure',
                'failure_count': self.failure_count + 1
            })
            
            error_message = str(e)
            self._create_log_entry('error', f'Task execution failed: {error_message}')
            
            return {'success': False, 'error': error_message}
    
    def _get_final_command(self):
        """Get the final command to execute based on task type and targets"""
        if self.task_type == 'docker_command' or self.task_type == 'system_command':
            return self.command
            
        elif self.task_type == 'container_action':
            if self.container_id:
                return self.command
            else:
                return 'docker ps -a'
                
        elif self.task_type == 'image_action':
            if self.image_id:
                return self.command
            else:
                return 'docker images'
                
        elif self.task_type == 'network_action':
            if self.network_id:
                return self.command
            else:
                return 'docker network ls'
                
        elif self.task_type == 'volume_action':
            if self.volume_id:
                return self.command
            else:
                return 'docker volume ls'
                
        elif self.task_type == 'prune_action':
            return self.command
            
        return self.command
    
    def _create_cron_job(self):
        """Create or update cron job for scheduled tasks"""
        self.ensure_one()
        
        if not self.cron_expr:
            return False
            
        # Check if cron job already exists
        if self.cron_id:
            # Update existing job
            self.cron_id.write({
                'active': self.active,
                'name': f'Docker Task: {self.name}',
                'model_id': self.env['ir.model'].search([('model', '=', 'docker.task')], limit=1).id,
                'state': 'code',
                'code': f'model.browse({self.id})._execute_task()',
                'interval_type': 'cron',
                'cron_name': self.cron_expr,
                'numbercall': -1,  # run indefinitely
                'doall': False,  # don't execute missed ones
                'user_id': self.env.user.id
            })
        else:
            # Create new job
            cron = self.env['ir.cron'].create({
                'active': self.active,
                'name': f'Docker Task: {self.name}',
                'model_id': self.env['ir.model'].search([('model', '=', 'docker.task')], limit=1).id,
                'state': 'code',
                'code': f'model.browse({self.id})._execute_task()',
                'interval_type': 'cron',
                'cron_name': self.cron_expr,
                'numbercall': -1,  # run indefinitely
                'doall': False,  # don't execute missed ones
                'user_id': self.env.user.id
            })
            self.cron_id = cron.id
        
        # Set next run time
        self.next_run = self.cron_id.nextcall
        return True
    
    def _create_log_entry(self, level, message):
        """Create a log entry for the task"""
        self.ensure_one()
        
        self.env['docker.logs'].create({
            'server_id': self.server_id.id,
            'task_id': self.id,
            'level': level,
            'name': message,
            'user_id': self.env.user.id,
        })