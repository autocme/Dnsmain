#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class StackMigrationWizard(models.TransientModel):
    _name = 'j_portainer.stack_migration_wizard'
    _description = 'Stack Migration/Duplication Wizard'

    source_stack_id = fields.Many2one(
        'j_portainer.stack',
        string='Source Stack',
        required=True,
        help="Stack to migrate or duplicate"
    )
    target_environment_id = fields.Many2one(
        'j_portainer.environment',
        string='Target Environment',
        required=True,
        help="Environment where the stack will be created"
    )
    target_server_id = fields.Many2one(
        'j_portainer.server',
        string='Target Server',
        compute='_compute_target_server',
        store=True,
        help="Server of the target environment"
    )
    new_stack_name = fields.Char(
        string='New Stack Name',
        required=True,
        help="Name for the new stack"
    )
    migration_type = fields.Selection([
        ('duplicate', 'Duplicate (Keep Original)'),
        ('migrate', 'Migrate (Move to New Environment)')
    ], string='Migration Type', default='duplicate', required=True)
    
    # Configuration fields from source stack
    source_compose_content = fields.Text(
        string='Docker Compose Content',
        readonly=True,
        help="Compose file content from source stack"
    )
    source_environment_variables = fields.Text(
        string='Environment Variables',
        readonly=True,
        help="Environment variables from source stack"
    )
    source_labels = fields.Text(
        string='Labels',
        readonly=True,
        help="Labels from source stack"
    )
    
    @api.depends('target_environment_id')
    def _compute_target_server(self):
        """Compute target server from target environment"""
        for wizard in self:
            wizard.target_server_id = wizard.target_environment_id.server_id.id if wizard.target_environment_id else False

    @api.onchange('source_stack_id')
    def _onchange_source_stack(self):
        """Load source stack configuration when source is selected"""
        if self.source_stack_id:
            self.new_stack_name = f"{self.source_stack_id.name}_copy"
            self.source_compose_content = self.source_stack_id.compose_content
            self.source_environment_variables = self.source_stack_id.environment_variables
            self.source_labels = self.source_stack_id.labels

    @api.model
    def default_get(self, fields_list):
        """Set default values from context"""
        result = super().default_get(fields_list)
        
        # Get source stack from context
        source_stack_id = self.env.context.get('active_id')
        if source_stack_id:
            source_stack = self.env['j_portainer.stack'].browse(source_stack_id)
            if source_stack.exists():
                result['source_stack_id'] = source_stack_id
                result['new_stack_name'] = f"{source_stack.name}_copy"
                result['source_compose_content'] = source_stack.compose_content
                result['source_environment_variables'] = source_stack.environment_variables
                result['source_labels'] = source_stack.labels
        
        return result

    @api.constrains('target_environment_id', 'source_stack_id')
    def _check_target_environment(self):
        """Validate target environment"""
        for wizard in self:
            if wizard.target_environment_id and wizard.source_stack_id:
                # Check if target environment is active
                if not wizard.target_environment_id.active:
                    raise ValidationError(_("Target environment must be active"))
                
                # Check if target environment is up
                if wizard.target_environment_id.status != 'up':
                    raise ValidationError(_("Target environment must be running"))
                
                # Check if target server is connected
                if wizard.target_environment_id.server_id.status != 'connected':
                    raise ValidationError(_("Target server must be connected"))

    @api.constrains('new_stack_name')
    def _check_stack_name(self):
        """Validate stack name"""
        for wizard in self:
            if wizard.new_stack_name and wizard.target_environment_id:
                # Check if stack name already exists in target environment
                existing_stack = self.env['j_portainer.stack'].search([
                    ('name', '=', wizard.new_stack_name),
                    ('environment_id', '=', wizard.target_environment_id.environment_id),
                    ('server_id', '=', wizard.target_environment_id.server_id.id)
                ])
                if existing_stack:
                    raise ValidationError(_("A stack with name '%s' already exists in the target environment") % wizard.new_stack_name)

    def action_migrate_stack(self):
        """Execute stack migration/duplication"""
        self.ensure_one()
        
        if not self.source_stack_id:
            raise UserError(_("Source stack is required"))
        
        if not self.target_environment_id:
            raise UserError(_("Target environment is required"))
        
        if not self.new_stack_name:
            raise UserError(_("New stack name is required"))
        
        try:
            # Prepare stack data for creation
            stack_vals = {
                'name': self.new_stack_name,
                'server_id': self.target_environment_id.server_id.id,
                'environment_id': self.target_environment_id.environment_id,
                'environment_name': self.target_environment_id.name,
                'compose_content': self.source_stack_id.compose_content,
                'environment_variables': self.source_stack_id.environment_variables or '',
                'labels': self.source_stack_id.labels or '',
                'type': self.source_stack_id.type,
                'status': 'inactive',  # Will be set by create method
                'active': True
            }
            
            # Create new stack (this will trigger API call to Portainer)
            new_stack = self.env['j_portainer.stack'].create(stack_vals)
            
            # If migration (not duplication), deactivate source stack
            if self.migration_type == 'migrate':
                # Stop and remove source stack from Portainer
                try:
                    self.source_stack_id.action_stop_stack()
                    self.source_stack_id.action_remove_stack()
                except Exception as e:
                    # Log warning but don't fail the migration
                    import logging
                    _logger = logging.getLogger(__name__)
                    _logger.warning(f"Could not remove source stack: {str(e)}")
                    
                    # Mark as inactive in Odoo
                    self.source_stack_id.write({
                        'active': False,
                        'status': 'inactive'
                    })
            
            # Return action to view the new stack
            return {
                'type': 'ir.actions.act_window',
                'name': _('Migrated Stack'),
                'res_model': 'j_portainer.stack',
                'res_id': new_stack.id,
                'view_mode': 'form',
                'target': 'current',
                'context': {
                    'form_view_initial_mode': 'readonly',
                }
            }
            
        except Exception as e:
            raise UserError(_("Stack migration failed: %s") % str(e))

    def action_cancel(self):
        """Cancel wizard"""
        return {'type': 'ir.actions.act_window_close'}