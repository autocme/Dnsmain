#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging
import re

_logger = logging.getLogger(__name__)

class PortainerContainerLogsWizard(models.TransientModel):
    _name = 'j_portainer.container.logs.wizard'
    _description = 'View Container Logs'
    
    container_id = fields.Many2one('j_portainer.container', string='Container', required=True, readonly=True)
    server_id = fields.Many2one('j_portainer.server', string='Server', related='container_id.server_id', readonly=True)
    name = fields.Char(related='container_id.name', readonly=True)
    environment_id = fields.Integer(related='container_id.environment_id', readonly=True)
    
    lines = fields.Integer('Number of Lines', default=100, required=True, 
                         help="Maximum number of log lines to retrieve. Use 0 for all logs (may be slow for large logs).")
    logs = fields.Text('Logs', readonly=True)
    
    @api.model
    def default_get(self, fields_list):
        """Set default values for the wizard"""
        res = super().default_get(fields_list)
        
        active_id = self.env.context.get('active_id')
        if active_id:
            container = self.env['j_portainer.container'].browse(active_id)
            res['container_id'] = container.id
            
            # Auto-fetch logs when wizard opens
            try:
                logs = self._fetch_logs(container, lines=100)
                res['logs'] = logs
            except Exception as e:
                _logger.error(f"Error fetching logs: {str(e)}")
                res['logs'] = f"Error fetching logs: {str(e)}"
                
        return res
    
    def _fetch_logs(self, container, lines=100):
        """Fetch logs from container
        
        Args:
            container: Container record
            lines: Number of lines to fetch
            
        Returns:
            str: Container logs
        """
        server = container.server_id
        endpoint_id = container.environment_id
        container_id = container.container_id
        
        # Build params
        params = {
            'tail': str(lines) if lines > 0 else 'all',
            'timestamps': True,
            'since': 0,
            'follow': False,
            'stdout': True,
            'stderr': True
        }
        
        # Make API request
        endpoint = f'/api/endpoints/{endpoint_id}/docker/containers/{container_id}/logs'
        response = server._make_api_request(endpoint, 'GET', params=params)
        
        if response.status_code != 200:
            raise UserError(_("Failed to get container logs: %s") % response.text)
            
        # Just return the raw logs without any formatting
        # Let the ACE editor handle display
        logs = response.text
        
        return logs
    
    def refresh_logs(self):
        """Refresh logs"""
        self.ensure_one()
        
        try:
            logs = self._fetch_logs(self.container_id, lines=self.lines)
            self.write({'logs': logs})
        except Exception as e:
            error_msg = _("Error fetching logs: %s") % str(e)
            self.write({'logs': error_msg})
            
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'j_portainer.container.logs.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }