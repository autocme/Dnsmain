#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging
import json

_logger = logging.getLogger(__name__)

class ContainerManageLabelsWizard(models.TransientModel):
    _name = 'j_portainer.container.manage.labels.wizard'
    _description = 'Manage Container Labels Wizard'
    
    container_id = fields.Many2one('j_portainer.container', string='Container', required=True,
                                   readonly=True, ondelete='cascade')
    server_id = fields.Many2one(related='container_id.server_id', string='Server', readonly=True)
    environment_id = fields.Integer(related='container_id.environment_id', string='Environment ID', readonly=True)
    environment_name = fields.Char(related='container_id.environment_name', string='Environment', readonly=True)
    
    # Raw labels JSON for bulk editing
    labels_json = fields.Text('Labels JSON', help="JSON format of labels (key-value pairs)")
    
    # Operation type
    operation = fields.Selection([
        ('edit', 'Edit Labels'),
        ('import', 'Import Labels'),
        ('export', 'Export Labels'),
    ], string='Operation', default='edit', required=True)
    
    @api.model
    def default_get(self, fields_list):
        """Set default values for wizard"""
        res = super(ContainerManageLabelsWizard, self).default_get(fields_list)
        
        # Get active container
        active_id = self.env.context.get('active_id')
        active_model = self.env.context.get('active_model')
        
        if active_model == 'j_portainer.container' and active_id:
            container = self.env['j_portainer.container'].browse(active_id)
            res['container_id'] = container.id
            
            # Get current labels and format as JSON
            labels = self.env['j_portainer.container.label'].search([
                ('container_id', '=', container.id)
            ])
            
            label_dict = {}
            for label in labels:
                label_dict[label.name] = label.value
                
            # Format with indentation for readability
            res['labels_json'] = json.dumps(label_dict, indent=2)
            
        return res
    
    def action_apply_labels(self):
        """Apply edited labels to container"""
        self.ensure_one()
        
        try:
            # Parse JSON labels
            new_labels = json.loads(self.labels_json or '{}')
            
            # Validate labels format
            if not isinstance(new_labels, dict):
                raise UserError(_("Labels must be a JSON object (key-value pairs)"))
                
            # Get current labels
            current_labels = self.env['j_portainer.container.label'].search([
                ('container_id', '=', self.container_id.id)
            ])
            
            # Create dictionary of current labels for comparison
            current_dict = {}
            for label in current_labels:
                current_dict[label.name] = label
                
            # Process labels to add or update
            labels_to_create = []
            labels_to_update = []
            
            for name, value in new_labels.items():
                if not name:
                    continue  # Skip empty names
                    
                if name in current_dict:
                    # Update existing label if value changed
                    if current_dict[name].value != str(value):
                        labels_to_update.append((current_dict[name], str(value)))
                else:
                    # Create new label
                    labels_to_create.append({
                        'container_id': self.container_id.id,
                        'name': name,
                        'value': str(value)
                    })
                    
            # Find labels to delete (in current but not in new)
            labels_to_delete = current_labels.filtered(lambda l: l.name not in new_labels)
            
            # Execute changes
            if labels_to_delete:
                labels_to_delete.unlink()
                
            if labels_to_create:
                self.env['j_portainer.container.label'].create(labels_to_create)
                
            for label, new_value in labels_to_update:
                label.write({'value': new_value})
                
            # Explicitly sync changes to Portainer
            _logger.info(f"Syncing label changes to Portainer for container {self.container_id.name}")
            try:
                # Call sync method on the container
                sync_result = self.container_id.sync_labels_to_portainer()
                
                if isinstance(sync_result, dict) and sync_result.get('params', {}).get('type') == 'success':
                    # Sync was successful
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Labels Updated'),
                            'message': _('Container labels have been updated and synced to Portainer successfully'),
                            'sticky': False,
                            'type': 'success',
                        }
                    }
                else:
                    # Sync failed but Odoo updates succeeded
                    _logger.warning(f"Sync to Portainer failed: {sync_result}")
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Labels Updated Partially'),
                            'message': _('Container labels were updated in Odoo but sync to Portainer may have failed. Check server logs for details.'),
                            'sticky': True,
                            'type': 'warning',
                        }
                    }
            except Exception as sync_err:
                _logger.error(f"Error syncing to Portainer: {str(sync_err)}")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Labels Updated Partially'),
                        'message': _('Container labels were updated in Odoo but sync to Portainer failed: %s') % str(sync_err),
                        'sticky': True,
                        'type': 'warning',
                    }
                }
            
        except json.JSONDecodeError:
            raise UserError(_("Invalid JSON format. Please check your input."))
        except Exception as e:
            raise UserError(_("Error applying labels: %s") % str(e))