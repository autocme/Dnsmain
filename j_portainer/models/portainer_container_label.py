#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)

class PortainerContainerLabel(models.Model):
    _name = 'j_portainer.container.label'
    _description = 'Portainer Container Label'
    _order = 'name'
    
    name = fields.Char('Label Name', required=True, index=True)
    value = fields.Char('Label Value', required=True)
    
    container_id = fields.Many2one('j_portainer.container', string='Container',
                                  required=True, ondelete='cascade', index=True)
    
    display_name = fields.Char('Display Name', compute='_compute_display_name')
    
    @api.depends('name', 'value')
    def _compute_display_name(self):
        """Compute display name for labels"""
        for label in self:
            label.display_name = f"{label.name}: {label.value}"
            
    @api.model_create_multi
    def create(self, vals_list):
        """Override create to sync new labels to Portainer"""
        records = super(PortainerContainerLabel, self).create(vals_list)
        
        # Group records by container for efficiency
        container_labels = {}
        for record in records:
            container_id = record.container_id.id
            if container_id not in container_labels:
                container_labels[container_id] = []
            container_labels[container_id].append(record)
            
        # Sync labels for each container
        for container_id, labels in container_labels.items():
            self._sync_container_labels_to_portainer(labels[0].container_id)
            
        return records
        
    def write(self, vals):
        """Override write to sync updated labels to Portainer"""
        result = super(PortainerContainerLabel, self).write(vals)
        
        # Get unique containers that need updating
        containers = self.mapped('container_id')
        
        # Sync labels for each container
        for container in containers:
            self._sync_container_labels_to_portainer(container)
            
        return result
        
    def unlink(self):
        """Override unlink to sync deleted labels to Portainer"""
        # Store containers before deletion
        containers = self.mapped('container_id')
        
        result = super(PortainerContainerLabel, self).unlink()
        
        # Sync labels for each container
        for container in containers:
            self._sync_container_labels_to_portainer(container)
            
        return result
        
    def _sync_container_labels_to_portainer(self, container):
        """Sync container labels to Portainer
        
        Args:
            container: Container record to sync labels for
        """
        try:
            # Get all current labels for this container
            all_labels = self.search([('container_id', '=', container.id)])
            
            # Convert to dictionary format for Portainer API
            label_dict = {}
            for label in all_labels:
                label_dict[label.name] = label.value
                
            # Call API to update container labels
            api = self.env['j_portainer.api']
            result = api.update_container_labels(
                container.server_id.id,
                container.environment_id,
                container.container_id,
                label_dict
            )
            
            if not result:
                _logger.warning(f"Failed to sync labels for container {container.name}")
                
        except Exception as e:
            _logger.error(f"Error syncing labels for container {container.name}: {str(e)}")