#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import json
import logging

_logger = logging.getLogger(__name__)

class PortainerNetworkDriverOption(models.Model):
    _name = 'j_portainer.network.driver.option'
    _description = 'Portainer Network Driver Option'
    
    name = fields.Char('Name', required=True, help="Option name, e.g. com.docker.network.bridge.enable_icc")
    value = fields.Char('Value', required=True, help="Option value, e.g. true")
    network_id = fields.Many2one('j_portainer.network', string='Network', required=True, ondelete='cascade')

class PortainerNetworkIPv4Excluded(models.Model):
    _name = 'j_portainer.network.ipv4.excluded'
    _description = 'Portainer Network IPv4 Excluded IP'
    
    ip_address = fields.Char('IP Address', required=True, help="IPv4 address to exclude")
    network_id = fields.Many2one('j_portainer.network', string='Network', required=True, ondelete='cascade')

class PortainerNetworkIPv6Excluded(models.Model):
    _name = 'j_portainer.network.ipv6.excluded'
    _description = 'Portainer Network IPv6 Excluded IP'
    
    ip_address = fields.Char('IP Address', required=True, help="IPv6 address to exclude")
    network_id = fields.Many2one('j_portainer.network', string='Network', required=True, ondelete='cascade')

class PortainerNetworkLabel(models.Model):
    _name = 'j_portainer.network.label'
    _description = 'Portainer Network Label'
    
    name = fields.Char('Name', required=True, help="Label name")
    value = fields.Char('Value', required=True, help="Label value")
    network_id = fields.Many2one('j_portainer.network', string='Network', required=True, ondelete='cascade')

class PortainerNetwork(models.Model):
    _name = 'j_portainer.network'
    _description = 'Portainer Network'
    _order = 'name'
    
    name = fields.Char('Name', required=True)
    network_id = fields.Char('Network ID', required=True)
    driver = fields.Selection([
        ('bridge', 'Bridge'),
        ('host', 'Host'),
        ('macvlan', 'MAC VLAN'),
        ('ipvlan', 'IP VLAN'),
        ('overlay', 'Overlay'),
        ('null', 'Null'),
    ], string='Driver', required=True, default='bridge',
       help="Supported network types: bridge (default), host, macvlan, ipvlan, overlay, null")
    scope = fields.Char('Scope', default='local')
    ipam = fields.Text('IPAM')
    ipam_config = fields.Html('IPAM Configuration', compute='_compute_ipam_config')
    containers = fields.Text('Containers')
    labels = fields.Text('Labels')
    details = fields.Text('Details')
    is_default_network = fields.Boolean('Default Network', default=False, 
                                       help="Default networks like 'bridge' and 'host' cannot be removed")
    is_ipv6 = fields.Boolean('IPv6 Enabled', default=False,
                            help="Whether IPv6 is enabled for this network")
    internal = fields.Boolean('Internal Network', default=False,
                             help="Whether the network is internal (no external connectivity)")
    isolated_network = fields.Boolean('Isolated network', default=False, 
                                  help="Toggle this option on to isolate any containers created in this network to this network only, with no inbound or outbound connectivity.")
    attachable = fields.Boolean('Enable manual container attachment', default=False,
                               help="Toggle this option on to allow users to attach the network to running containers.")
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
    last_sync = fields.Datetime('Last Synchronized', readonly=True)
    
    # Related containers connected to this network
    connected_container_ids = fields.One2many('j_portainer.container.network', 'network_id', string='Connected Containers')
    
    # Driver options
    driver_option_ids = fields.One2many('j_portainer.network.driver.option', 'network_id', string='Driver Options')
    
    # IPv4 Configuration
    ipv4_subnet = fields.Char('IPv4 Subnet', help="CIDR notation for IPv4 subnet (e.g. 172.17.0.0/16)")
    ipv4_gateway = fields.Char('IPv4 Gateway', help="IPv4 gateway address")
    ipv4_range = fields.Char('IPv4 Range', help="IPv4 address range in CIDR notation")
    ipv4_excluded_ids = fields.One2many('j_portainer.network.ipv4.excluded', 'network_id', string='IPv4 Excluded IPs')
    
    # IPv6 Configuration
    ipv6_subnet = fields.Char('IPv6 Subnet', help="CIDR notation for IPv6 subnet")
    ipv6_gateway = fields.Char('IPv6 Gateway', help="IPv6 gateway address")
    ipv6_range = fields.Char('IPv6 Range', help="IPv6 address range in CIDR notation")
    ipv6_excluded_ids = fields.One2many('j_portainer.network.ipv6.excluded', 'network_id', string='IPv6 Excluded IPs')
    
    # Network Labels
    network_label_ids = fields.One2many('j_portainer.network.label', 'network_id', string='Network Labels')
    
    def _get_api(self):
        """Get API client"""
        return self.env['j_portainer.api']
    
    def _compute_ipam_config(self):
        """Compute formatted IPAM configuration from the ipam field"""
        for record in self:
            if not record.ipam:
                record.ipam_config = '<p>No IPAM configuration available</p>'
                continue
                
            try:
                # Just display the raw IPAM data in a pre-formatted block
                ipam_data = json.loads(record.ipam) or {}
                
                # Pretty-print the JSON for better readability
                formatted_json = json.dumps(ipam_data, indent=2)
                
                # Convert to HTML-friendly format
                formatted_html = f'<pre>{formatted_json}</pre>'
                record.ipam_config = formatted_html
            except Exception as e:
                record.ipam_config = f'<p>Error parsing IPAM data: {str(e)}</p>'
    
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
        
        # Store network information before attempting to delete
        network_name = self.name
        
        try:
            api = self._get_api()
            result = api.network_action(
                self.server_id.id, self.environment_id, self.network_id, 'delete')
            
            # Check for errors in the result - be very explicit about this check
            if isinstance(result, dict) and result.get('error'):
                error_message = result.get('error')
                _logger.error(f"Failed to remove network {self.name} from Portainer: {error_message}")
                raise UserError(_(f"Failed to remove network: {error_message}"))
                
            # Only consider it a success if result is a dict with success=True
            # or if result is True (for backward compatibility)
            if (isinstance(result, dict) and result.get('success')) or result is True:
                # Only delete the Odoo record if Portainer deletion was successful
                # Create success notification first, before deleting the record
                message = {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Network Removed'),
                        'message': _('Network %s removed successfully') % network_name,
                        'sticky': False,
                        'type': 'success',
                    }
                }
                
                # Now delete the record
                self.unlink()
                self.env.cr.commit()
                
                return message
            else:
                # If Portainer deletion returned an unexpected result, don't delete from Odoo
                _logger.error(f"Unexpected result when removing network {self.name} from Portainer: {result}")
                raise UserError(_("Failed to remove network from Portainer - unexpected response"))
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