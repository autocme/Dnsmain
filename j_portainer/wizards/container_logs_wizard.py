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
    environment_id = fields.Many2one(related='container_id.environment_id', readonly=True)
    
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
                # Extra safety check for NUL characters
                if logs and isinstance(logs, str):
                    logs = logs.replace('\x00', '')
                res['logs'] = logs
            except ValueError as ve:
                if "NUL" in str(ve):
                    # Specific handling for NUL characters
                    _logger.error(f"NUL character detected in logs: {str(ve)}")
                    error_msg = _("""Error: Container logs contain NUL (0x00) characters that cannot be displayed.
                    
Suggestions:
1. Try reducing the number of lines
2. For binary logs, you may need to use the Portainer UI directly
3. Check if the container outputs binary data instead of text logs
""")
                    res['logs'] = error_msg
                else:
                    _logger.error(f"ValueError processing logs: {str(ve)}")
                    res['logs'] = f"Error processing logs: {str(ve)}"
            except Exception as e:
                _logger.error(f"Error fetching logs: {str(e)}")
                res['logs'] = f"Error fetching logs: {str(e)}"
                
        return res
    
    def _clean_binary_data(self, data):
        """Clean binary data to make it suitable for storing in a string field
        
        Args:
            data: Binary data to clean
            
        Returns:
            str: Cleaned data as a string
        """
        try:
            # Try to decode as UTF-8 first
            if isinstance(data, bytes):
                # First remove any NUL bytes from the binary data
                data = data.replace(b'\x00', b'')
                text = data.decode('utf-8', errors='replace')
            else:
                text = str(data)
                
            # Remove NUL characters - double check as a safety measure
            text = text.replace('\x00', '')
            
            # Replace other control characters except newlines and tabs
            text = re.sub(r'[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]', ' ', text)
            
            # Final check for any remaining NUL characters (just to be extra safe)
            if '\x00' in text:
                text = text.replace('\x00', '')
                
            return text
        except Exception as e:
            _logger.error(f"Error cleaning binary data: {str(e)}")
            return "Error: Unable to process binary log data"
    
    def _fetch_logs(self, container, lines=100):
        """Fetch logs from container
        
        Args:
            container: Container record
            lines: Number of lines to fetch
            
        Returns:
            str: Container logs
        """
        server = container.server_id
        endpoint_id = container.environment_id.environment_id  # Get the actual numeric ID
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
            
        # Process the logs to remove problematic characters
        try:
            # Check if we have a binary response (can happen with some Docker logs)
            if hasattr(response, 'content') and isinstance(response.content, bytes):
                logs = self._clean_binary_data(response.content)
            else:
                logs = self._clean_binary_data(response.text)
                
        except Exception as e:
            _logger.error(f"Error processing logs: {str(e)}")
            # If there's any error processing the text, return a safe version
            logs = "Error processing container logs, received logs contain invalid characters."
            
        return logs
    
    def refresh_logs(self):
        """Refresh logs"""
        self.ensure_one()
        
        try:
            logs = self._fetch_logs(self.container_id, lines=self.lines)
            
            # Multiple safety checks before writing to database
            if logs and isinstance(logs, str):
                # Remove any remaining NUL characters at every level
                logs = logs.replace('\x00', '')
                
                # Check again - if there are still NUL characters somehow,
                # handle it with a more explicit approach
                if '\x00' in logs:
                    _logger.warning("NUL characters still detected after cleaning, using stronger replacement")
                    logs = ''.join(char for char in logs if char != '\x00')
            
            self.write({'logs': logs})
        except ValueError as ve:
            if "NUL" in str(ve):
                # Specific handling for NUL characters
                _logger.error(f"NUL character detected in logs: {str(ve)}")
                error_msg = _("""Error: Container logs contain NUL (0x00) characters that cannot be displayed.
                
Suggestions:
1. Try reducing the number of lines (current: %s)
2. For binary logs, you may need to use the Portainer UI directly
3. Check if the container outputs binary data instead of text logs
""") % self.lines
                self.write({'logs': error_msg})
            else:
                # Other ValueError handling
                _logger.error(f"ValueError processing logs: {str(ve)}")
                error_msg = _("Error processing logs: %s") % str(ve)
                self.write({'logs': error_msg})
        except Exception as e:
            # General exception handling
            _logger.error(f"Error fetching logs: {str(e)}")
            error_msg = _("Error fetching logs: %s") % str(e)
            self.write({'logs': error_msg})
            
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'j_portainer.container.logs.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }