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
            
        # Process logs to improve readability
        logs = response.text
        
        # Add colors based on log level (using ANSI escape codes for ACE editor)
        if logs:
            # Color error lines in red
            logs = logs.replace('[error]', '\u001b[31m[ERROR]\u001b[0m')
            logs = logs.replace('ERROR:', '\u001b[31mERROR:\u001b[0m')
            
            # Color warning lines in yellow
            logs = logs.replace('[warn]', '\u001b[33m[WARN]\u001b[0m')
            logs = logs.replace('WARNING:', '\u001b[33mWARNING:\u001b[0m')
            
            # Color info lines in blue
            logs = logs.replace('[info]', '\u001b[34m[INFO]\u001b[0m')
            logs = logs.replace('INFO:', '\u001b[34mINFO:\u001b[0m')
            
            # Format timestamps in green
            timestamp_pattern = r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})'
            logs = re.sub(timestamp_pattern, r'\u001b[32m\1\u001b[0m', logs)
        
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