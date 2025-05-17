#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import json
import logging

_logger = logging.getLogger(__name__)

class PortainerNetwork(models.Model):
    _name = 'j_portainer.network'
    _description = 'Portainer Network'
    _order = 'name'
    
    name = fields.Char('Name', required=True)
    network_id = fields.Char('Network ID', required=True)
    driver = fields.Char('Driver', required=True)
    scope = fields.Char('Scope', default='local')
    ipam = fields.Text('IPAM')
    ipam_config = fields.Text('IPAM Configuration') # Field to hold formatted IPAM configuration for display
    containers = fields.Text('Containers')
    labels = fields.Text('Labels')
    details = fields.Text('Details')
    is_default_network = fields.Boolean('Default Network', default=False, 
                                       help="Default networks like 'bridge' and 'host' cannot be removed")
    is_ipv6 = fields.Boolean('IPv6 Enabled', default=False,
                            help="Whether IPv6 is enabled for this network")
    internal = fields.Boolean('Internal Network', default=False,
                             help="Whether the network is internal (no external connectivity)")
    attachable = fields.Boolean('Attachable', default=False,
                               help="Whether containers can be attached to this network")
    public = fields.Boolean('Public', default=True,
                          help="Whether the network is publicly accessible")
    administrators_only = fields.Boolean('Administrators Only', default=False,
                                      help="Whether only administrators can use this network")
    system = fields.Boolean('System', default=False,
                          help="Whether this is a system-managed network")
    options = fields.Text('Options')
    options_html = fields.Html('Options HTML', compute='_compute_options_html')
    
    server_id = fields.Many2one('j_portainer.server', string='Server', required=True, ondelete='cascade')
    environment_id = fields.Integer('Environment ID', required=True)
    environment_name = fields.Char('Environment', required=True)
    
    # Related containers connected to this network
    connected_container_ids = fields.One2many('j_portainer.container.network', 'network_id', string='Connected Containers')
    
    def _get_api(self):
        """Get API client"""
        return self.env['j_portainer.api']
    
    def get_formatted_details(self):
        """Get formatted network details"""
        self.ensure_one()
        if not self.details:
            return ''
            
        try:
            details_data = json.loads(self.details)
            result = []
            
            # Extract key information
            if 'IPAM' in details_data and 'Config' in details_data['IPAM']:
                configs = details_data['IPAM']['Config']
                if configs:
                    result.append("IPAM Configuration:")
                    for config in configs:
                        if 'Subnet' in config:
                            result.append(f"  Subnet: {config['Subnet']}")
                        if 'Gateway' in config:
                            result.append(f"  Gateway: {config['Gateway']}")
                            
            # Extract some other useful properties
            if 'Internal' in details_data and details_data['Internal']:
                result.append("Internal: Yes")
                
            if 'Attachable' in details_data and details_data['Attachable']:
                result.append("Attachable: Yes")
                
            if 'EnableIPv6' in details_data and details_data['EnableIPv6']:
                result.append("IPv6 Enabled: Yes")
                
            return '\n'.join(result)
        except Exception as e:
            _logger.error(f"Error formatting details: {str(e)}")
            return self.details
    
    def get_formatted_containers(self):
        """Get formatted container list"""
        self.ensure_one()
        if not self.containers:
            return ''
            
        try:
            containers_data = json.loads(self.containers)
            if not containers_data:
                return ''
                
            result = []
            for container_id, container_info in containers_data.items():
                name = container_info.get('Name', container_id[:12])
                ipv4 = container_info.get('IPv4Address', '')
                ipv6 = container_info.get('IPv6Address', '')
                
                if ipv4 and ipv6:
                    result.append(f"{name}: {ipv4}, {ipv6}")
                elif ipv4:
                    result.append(f"{name}: {ipv4}")
                elif ipv6:
                    result.append(f"{name}: {ipv6}")
                else:
                    result.append(name)
                    
            return '\n'.join(result)
        except Exception as e:
            _logger.error(f"Error formatting containers: {str(e)}")
            return self.containers
            
    def get_formatted_ipam(self):
        """Get formatted IPAM configuration"""
        self.ensure_one()
        if not self.ipam:
            return ''
            
        try:
            ipam_data = json.loads(self.ipam)
            if not ipam_data or 'Config' not in ipam_data:
                return ''
                
            configs = ipam_data['Config']
            result = []
            
            for config in configs:
                if 'Subnet' in config:
                    if 'Gateway' in config:
                        result.append(f"{config['Subnet']} (Gateway: {config['Gateway']})")
                    else:
                        result.append(config['Subnet'])
                        
            return '\n'.join(result)
        except Exception as e:
            _logger.error(f"Error formatting IPAM: {str(e)}")
            return self.ipam
            
    def get_formatted_labels(self):
        """Get formatted network labels"""
        self.ensure_one()
        if not self.labels:
            return ''
            
        try:
            labels_data = json.loads(self.labels)
            formatted_labels = [f"{key}: {value}" for key, value in labels_data.items()]
            return '\n'.join(formatted_labels)
        except Exception as e:
            _logger.error(f"Error formatting labels: {str(e)}")
            return self.labels
    
    def remove(self):
        """Remove the network"""
        self.ensure_one()
        
        try:
            api = self._get_api()
            result = api.network_action(
                self.server_id.id, self.environment_id, self.network_id, 'delete')
                
            if result:
                # Delete the record
                self.unlink()
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Network Removed'),
                        'message': _('Network %s removed successfully') % self.name,
                        'sticky': False,
                        'type': 'success',
                    }
                }
            else:
                raise UserError(_("Failed to remove network"))
        except Exception as e:
            _logger.error(f"Error removing network {self.name}: {str(e)}")
            raise UserError(_("Error removing network: %s") % str(e))
    
    def action_remove(self):
        """Action to remove the network from the UI"""
        return self.remove()
    
    def action_refresh(self):
        """Refresh network information"""
        self.ensure_one()
        
        try:
            self.server_id.sync_networks(self.environment_id)
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Network Refreshed'),
                    'message': _('Network information refreshed successfully'),
                    'sticky': False,
                    'type': 'success',
                }
            }
        except Exception as e:
            _logger.error(f"Error refreshing network {self.name}: {str(e)}")
            raise UserError(_("Error refreshing network: %s") % str(e))
    
    @api.depends('options')
    def _compute_options_html(self):
        """Format network options as HTML table"""
        for record in self:
            if not record.options or record.options == '{}':
                record.options_html = '<p>No options available</p>'
                continue
                
            try:
                options_data = json.loads(record.options)
                if not options_data:
                    record.options_html = '<p>No options available</p>'
                    continue
                    
                html = ['<table class="table table-sm table-bordered">',
                        '<thead><tr><th>Option</th><th>Value</th></tr></thead>',
                        '<tbody>']
                        
                for key, value in options_data.items():
                    html.append(f'<tr><td>{key}</td><td>{value}</td></tr>')
                    
                html.append('</tbody></table>')
                record.options_html = ''.join(html)
            except Exception as e:
                _logger.error(f"Error formatting options HTML: {str(e)}")
                record.options_html = f'<p>Error formatting options: {str(e)}</p>'
    
    @api.model
    def create_network(self, server_id, environment_id, name, driver='bridge', subnet=None, gateway=None, internal=False, attachable=False, enable_ipv6=False, labels=None):
        """Create a new network
        
        Args:
            server_id: ID of the server to create the network on
            environment_id: ID of the environment to create the network on
            name: Name of the network
            driver: Network driver (default: 'bridge')
            subnet: CIDR subnet for the network (optional)
            gateway: Gateway IP address (optional)
            internal: Whether the network is internal (default: False)
            attachable: Whether the network is attachable (default: False)
            enable_ipv6: Whether to enable IPv6 (default: False)
            labels: Dictionary of labels to apply to the network (optional)
            
        Returns:
            bool: True if successful
        """
        try:
            server = self.env['j_portainer.server'].browse(server_id)
            if not server:
                return False
                
            # Prepare data for network creation
            data = {
                'Name': name,
                'Driver': driver,
                'Internal': internal,
                'Attachable': attachable,
                'EnableIPv6': enable_ipv6,
                'CheckDuplicate': True
            }
            
            # Add IPAM configuration if subnet is provided
            if subnet:
                ipam_config = {
                    'Subnet': subnet
                }
                
                if gateway:
                    ipam_config['Gateway'] = gateway
                    
                data['IPAM'] = {
                    'Driver': 'default',
                    'Config': [ipam_config]
                }
                
            if labels:
                data['Labels'] = labels
                
            # Make API request to create network
            endpoint = f'/api/endpoints/{environment_id}/docker/networks/create'
            response = server._make_api_request(endpoint, 'POST', data=data)
            
            if response.status_code in [200, 201, 204]:
                # Refresh networks
                server.sync_networks(environment_id)
                return True
            else:
                _logger.error(f"Failed to create network: {response.text}")
                return False
                
        except Exception as e:
            _logger.error(f"Error creating network {name}: {str(e)}")
            return False