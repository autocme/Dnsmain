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
    
    @api.model_create_multi
    def create(self, vals_list):
        """Override create to create networks in Portainer when created in Odoo"""
        # First create the records in Odoo
        records = super(PortainerNetwork, self).create(vals_list)

        # Then try to create the networks in Portainer
        for record in records:
            record.create_network_in_portainer()

        return records

    def create_network_in_portainer(self, from_sync=False):
        self.ensure_one()
        try:
            # If a network_id is already provided, this is likely a sync operation
            # so we should not try to create a new network in Portainer
            if self.network_id:
                if from_sync:
                    # During sync, just return without error
                    return False
                else:
                    raise UserError(
                        _('The Network Already Has an ID, which means its already created, cant create a network if the ID is existed'))

            # Create the network in Portainer
            data = {
                'Name': self.name,
                'Driver': self.driver,
                'Internal': self.internal,
                'Attachable': self.attachable,
                'EnableIPv6': self.is_ipv6,
                'CheckDuplicate': True
            }

            # Add IPAM configuration if subnet is provided
            ipam_configs = []

            # Add IPv4 configuration if present
            if self.ipv4_subnet:
                ipv4_config = {
                    'Subnet': self.ipv4_subnet
                }

                if self.ipv4_gateway:
                    ipv4_config['Gateway'] = self.ipv4_gateway

                if self.ipv4_range:
                    ipv4_config['IPRange'] = self.ipv4_range

                # Add excluded IPs if present
                if self.ipv4_excluded_ids:
                    ipv4_config['ExcludedIPs'] = [ip.ip_address for ip in self.ipv4_excluded_ids]

                ipam_configs.append(ipv4_config)

            # Add IPv6 configuration if present
            if self.ipv6_subnet:
                ipv6_config = {
                    'Subnet': self.ipv6_subnet
                }

                if self.ipv6_gateway:
                    ipv6_config['Gateway'] = self.ipv6_gateway

                if self.ipv6_range:
                    ipv6_config['IPRange'] = self.ipv6_range

                # Add excluded IPs if present
                if self.ipv6_excluded_ids:
                    ipv6_config['ExcludedIPs'] = [ip.ip_address for ip in self.ipv6_excluded_ids]

                ipam_configs.append(ipv6_config)

            # Add IPAM configuration if we have any configs
            if ipam_configs:
                data['IPAM'] = {
                    'Driver': 'default',
                    'Config': ipam_configs
                }

            # Add labels if present
            if self.network_label_ids:
                data['Labels'] = {label.name: label.value for label in self.network_label_ids}

            # Add driver options if present
            if self.driver_option_ids:
                data['Options'] = {option.name: option.value for option in self.driver_option_ids}

            # Make API request to create network
            server = self.server_id
            environment_id = self.environment_id.environment_id
            endpoint = f'/api/endpoints/{environment_id}/docker/networks/create'

            # Log the data being sent for debugging
            _logger.info(f"Creating network with data: {data}")

            response = server._make_api_request(endpoint, 'POST', data=data)

            if response.status_code in [200, 201, 204]:
                # Get the network ID from the response
                response_data = response.json()
                network_id = response_data.get('Id')

                if network_id:
                    # Get detailed network information from Portainer to sync all fields
                    details_response = server._make_api_request(
                        f'/api/endpoints/{environment_id}/docker/networks/{network_id}', 'GET')
                    
                    if details_response.status_code == 200:
                        details = details_response.json()
                        
                        # Extract IPAM configuration
                        ipam_data = details.get('IPAM', {})
                        ipam_config = ipam_data.get('Config', [])
                        
                        # Initialize IPv4 and IPv6 values
                        ipv4_subnet = ipv4_gateway = ipv4_range = None
                        ipv6_subnet = ipv6_gateway = ipv6_range = None
                        
                        # Parse IPAM configuration for IPv4 and IPv6
                        for config in ipam_config:
                            subnet = config.get('Subnet', '')
                            if ':' in subnet:  # IPv6
                                ipv6_subnet = subnet
                                ipv6_gateway = config.get('Gateway')
                                ipv6_range = config.get('IPRange')
                            else:  # IPv4
                                ipv4_subnet = subnet
                                ipv4_gateway = config.get('Gateway')
                                ipv4_range = config.get('IPRange')
                        
                        # Update the record with all network details
                        update_data = {
                            'network_id': network_id,
                            'driver': details.get('Driver', self.driver),
                            'scope': details.get('Scope', 'local'),
                            'is_ipv6': details.get('EnableIPv6', False),
                            'internal': details.get('Internal', False),
                            'attachable': details.get('Attachable', False),
                            'ipam': json.dumps(ipam_data),
                            'labels': json.dumps(details.get('Labels') or {}),
                            'containers': json.dumps(details.get('Containers') or {}),
                            'details': json.dumps(details, indent=2),
                            'options': json.dumps(details.get('Options') or {}),
                            'last_sync': fields.Datetime.now()
                        }
                        
                        # Add IPv4 configuration if available
                        if ipv4_subnet:
                            update_data['ipv4_subnet'] = ipv4_subnet
                        if ipv4_gateway:
                            update_data['ipv4_gateway'] = ipv4_gateway
                        if ipv4_range:
                            update_data['ipv4_range'] = ipv4_range
                            
                        # Add IPv6 configuration if available
                        if ipv6_subnet:
                            update_data['ipv6_subnet'] = ipv6_subnet
                        if ipv6_gateway:
                            update_data['ipv6_gateway'] = ipv6_gateway
                        if ipv6_range:
                            update_data['ipv6_range'] = ipv6_range
                        
                        self.write(update_data)
                        
                        # Check if all requested configurations were applied and notify user
                        warnings = []
                        if self.ipv4_subnet and not ipv4_subnet:
                            warnings.append("IPv4 subnet configuration may not have been applied")
                        if self.ipv6_subnet and not ipv6_subnet:
                            warnings.append("IPv6 subnet configuration may not have been applied")
                        
                        # Show success message with any warnings
                        message_text = _('Network %s created successfully in Portainer') % self.name
                        if warnings:
                            message_text += ". " + _("Note: %s") % "; ".join(warnings)
                            
                        return {
                            'type': 'ir.actions.client',
                            'tag': 'display_notification',
                            'params': {
                                'title': _('Network Created'),
                                'message': message_text,
                                'sticky': False,
                                'type': 'warning' if warnings else 'success',
                            }
                        }
                    else:
                        # Network created but couldn't get details
                        self.write({
                            'network_id': network_id,
                            'last_sync': fields.Datetime.now()
                        })
                        
                        return {
                            'type': 'ir.actions.client',
                            'tag': 'display_notification',
                            'params': {
                                'title': _('Network Created'),
                                'message': _('Network %s created in Portainer but could not retrieve all details') % self.name,
                                'sticky': False,
                                'type': 'warning',
                            }
                        }
                else:
                    # Handle case where network ID is not returned
                    if from_sync:
                        _logger.warning("Network created in Portainer but no ID was returned")
                        return False
                    else:
                        raise UserError(_("Network created in Portainer but no ID was returned"))
            else:
                # If creation failed, raise an error and prevent saving
                error_msg = response.text
                if from_sync:
                    _logger.warning(f"Failed to create network in Portainer during sync: {error_msg}")
                    return False
                else:
                    raise UserError(_("Failed to create network in Portainer: %s") % error_msg)

        except Exception as e:
            # If an error occurred, handle based on context
            if from_sync:
                _logger.warning(f"Error creating network in Portainer during sync: {str(e)}")
                return False
            else:
                raise UserError(_("Error creating network in Portainer: %s") % str(e))
    
    name = fields.Char('Name', required=True)
    network_id = fields.Char('Network ID', readonly=True)
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
    
    server_id = fields.Many2one('j_portainer.server', string='Server', required=True)
    environment_id = fields.Many2one('j_portainer.environment', string='Environment', required=True)
    last_sync = fields.Datetime('Last Synchronized', readonly=True)
    
    # Related containers connected to this network
    connected_container_ids = fields.One2many('j_portainer.container.network', 'network_id', string='Connected Containers', ondelete='cascade')
    
    # Driver options
    driver_option_ids = fields.One2many('j_portainer.network.driver.option', 'network_id', string='Driver Options', ondelete='cascade')
    
    # IPv4 Configuration
    ipv4_subnet = fields.Char('IPv4 Subnet', help="CIDR notation for IPv4 subnet (e.g. 172.17.0.0/16)")
    ipv4_gateway = fields.Char('IPv4 Gateway', help="IPv4 gateway address")
    ipv4_range = fields.Char('IPv4 Range', help="IPv4 address range in CIDR notation")
    ipv4_excluded_ids = fields.One2many('j_portainer.network.ipv4.excluded', 'network_id', string='IPv4 Excluded IPs', ondelete='cascade')
    
    # IPv6 Configuration
    ipv6_subnet = fields.Char('IPv6 Subnet', help="CIDR notation for IPv6 subnet")
    ipv6_gateway = fields.Char('IPv6 Gateway', help="IPv6 gateway address")
    ipv6_range = fields.Char('IPv6 Range', help="IPv6 address range in CIDR notation")
    ipv6_excluded_ids = fields.One2many('j_portainer.network.ipv6.excluded', 'network_id', string='IPv6 Excluded IPs', ondelete='cascade')
    
    # Network Labels
    network_label_ids = fields.One2many('j_portainer.network.label', 'network_id', string='Network Labels', ondelete='cascade')
    
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
    

            

    
    def remove(self):
        """Remove the network"""
        self.ensure_one()
        
        # Store network information before attempting to delete
        network_name = self.name
        
        try:
            api = self._get_api()
            result = api.network_action(
                self.server_id.id, self.environment_id.environment_id, self.network_id, 'delete')
            
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
            self.server_id.sync_networks(self.environment_id.environment_id)
            
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