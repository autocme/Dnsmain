#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class PortainerSyncWizard(models.TransientModel):
    _name = 'j_portainer.sync.wizard'
    _description = 'Portainer Synchronization Wizard'
    
    server_id = fields.Many2one('j_portainer.server', string='Server', required=True)
    sync_all = fields.Boolean('Sync All Resources', default=True)
    
    # What to sync
    sync_environments = fields.Boolean('Environments', default=True)
    sync_containers = fields.Boolean('Containers', default=True)
    sync_images = fields.Boolean('Images', default=True)
    sync_volumes = fields.Boolean('Volumes', default=True)
    sync_networks = fields.Boolean('Networks', default=True)
    sync_stacks = fields.Boolean('Stacks', default=True)
    sync_templates = fields.Boolean('Templates', default=True, help="For backward compatibility")
    sync_standard_templates = fields.Boolean('Standard Templates', default=True)
    sync_custom_templates = fields.Boolean('Custom Templates', default=True)
    
    # Sync specific environment
    environment_specific = fields.Boolean('Sync Specific Environment Only', default=False)
    environment_id = fields.Many2one('j_portainer.environment', string='Environment', 
                                   domain="[('server_id', '=', server_id)]")
    
    # Results
    state = fields.Selection([
        ('draft', 'Draft'),
        ('running', 'Running'),
        ('done', 'Done')
    ], default='draft')
    sync_log = fields.Text('Synchronization Log', readonly=True)
    
    @api.onchange('sync_all')
    def _onchange_sync_all(self):
        """Handle sync_all change"""
        if self.sync_all:
            self.sync_environments = True
            self.sync_containers = True
            self.sync_images = True
            self.sync_volumes = True
            self.sync_networks = True
            self.sync_stacks = True
            self.sync_templates = True
            self.sync_standard_templates = True
            self.sync_custom_templates = True
            
    @api.onchange('environment_specific')
    def _onchange_environment_specific(self):
        """Handle environment_specific change"""
        if not self.environment_specific:
            self.environment_id = False
    
    def _append_log(self, message):
        """Append message to sync log"""
        if self.sync_log:
            self.sync_log = f"{self.sync_log}\n{message}"
        else:
            self.sync_log = message
            
    def action_sync(self):
        """Start synchronization"""
        self.ensure_one()
        
        if not self.server_id:
            raise UserError(_("Please select a server"))
            
        if self.environment_specific and not self.environment_id:
            raise UserError(_("Please select an environment"))
            
        self.write({
            'state': 'running',
            'sync_log': _('Starting synchronization...')
        })
        
        server = self.server_id
        env_id = self.environment_id.environment_id if self.environment_specific else None
        
        try:
            # First, test connection to make sure the server is accessible
            self._append_log(_('Testing connection to server...'))
            server.test_connection()
            self._append_log(_('Connection successful!'))
            
            # Sync environments first if requested
            if self.sync_environments and not self.environment_specific:
                self._append_log(_('Synchronizing environments...'))
                result = server.sync_environments()
                if 'params' in result and 'message' in result['params']:
                    self._append_log(result['params']['message'])
                else:
                    self._append_log(_('Environments synchronized'))
                    
            # Sync templates if requested (for backward compatibility)
            if self.sync_templates and not self.environment_specific:
                self._append_log(_('Synchronizing all templates...'))
                result = server.sync_templates()
                if 'params' in result and 'message' in result['params']:
                    self._append_log(result['params']['message'])
                else:
                    self._append_log(_('All templates synchronized'))
            else:
                # Sync standard templates if requested
                if self.sync_standard_templates and not self.environment_specific:
                    self._append_log(_('Synchronizing standard templates...'))
                    result = server.sync_standard_templates()
                    if 'params' in result and 'message' in result['params']:
                        self._append_log(result['params']['message'])
                    else:
                        self._append_log(_('Standard templates synchronized'))
                
                # Sync custom templates if requested
                if self.sync_custom_templates and not self.environment_specific:
                    self._append_log(_('Synchronizing custom templates...'))
                    result = server.sync_custom_templates()
                    if 'params' in result and 'message' in result['params']:
                        self._append_log(result['params']['message'])
                    else:
                        self._append_log(_('Custom templates synchronized'))
                    
            # Sync containers if requested
            if self.sync_containers:
                self._append_log(_('Synchronizing containers...'))
                result = server.sync_containers(env_id)
                if 'params' in result and 'message' in result['params']:
                    self._append_log(result['params']['message'])
                else:
                    self._append_log(_('Containers synchronized'))
                    
            # Sync images if requested
            if self.sync_images:
                self._append_log(_('Synchronizing images...'))
                result = server.sync_images(env_id)
                if 'params' in result and 'message' in result['params']:
                    self._append_log(result['params']['message'])
                else:
                    self._append_log(_('Images synchronized'))
                    
            # Sync volumes if requested
            if self.sync_volumes:
                self._append_log(_('Synchronizing volumes...'))
                result = server.sync_volumes(env_id)
                if 'params' in result and 'message' in result['params']:
                    self._append_log(result['params']['message'])
                else:
                    self._append_log(_('Volumes synchronized'))
                    
            # Sync networks if requested
            if self.sync_networks:
                self._append_log(_('Synchronizing networks...'))
                result = server.sync_networks(env_id)
                if 'params' in result and 'message' in result['params']:
                    self._append_log(result['params']['message'])
                else:
                    self._append_log(_('Networks synchronized'))
                    
            # Sync stacks if requested
            if self.sync_stacks:
                self._append_log(_('Synchronizing stacks...'))
                result = server.sync_stacks(env_id)
                if 'params' in result and 'message' in result['params']:
                    self._append_log(result['params']['message'])
                else:
                    self._append_log(_('Stacks synchronized'))
                    
            # Mark as done
            self.write({
                'state': 'done',
                'sync_log': f"{self.sync_log}\n\n{_('Synchronization completed successfully!')}"
            })
            
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'j_portainer.sync.wizard',
                'res_id': self.id,
                'view_mode': 'form',
                'target': 'new',
            }
            
        except Exception as e:
            _logger.error(f"Error during synchronization: {str(e)}")
            self.write({
                'state': 'done',
                'sync_log': f"{self.sync_log}\n\n{_('Error during synchronization: %s') % str(e)}"
            })
            
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'j_portainer.sync.wizard',
                'res_id': self.id,
                'view_mode': 'form',
                'target': 'new',
            }