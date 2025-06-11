#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


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
    
    handle_dependencies = fields.Selection([
        ('ignore', 'Ignore Missing Dependencies (May Fail)'),
        ('create_missing', 'Create Missing Networks (Recommended)'),
        ('abort', 'Abort if Dependencies Missing')
    ], string='Handle Dependencies', default='create_missing', required=True,
       help="How to handle missing external networks and volumes")
    
    # Configuration fields from source stack
    source_content = fields.Text(
        string='Docker Compose Content',
        readonly=True,
        help="Compose file content from source stack"
    )
    source_file_content = fields.Text(
        string='Stack File Content',
        readonly=True,
        help="Stack file content from source stack"
    )
    source_details = fields.Text(
        string='Stack Details',
        readonly=True,
        help="Stack details from source stack"
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
            self.source_content = self.source_stack_id.content
            self.source_file_content = self.source_stack_id.file_content
            self.source_details = self.source_stack_id.details

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
                result['source_content'] = source_stack.content
                result['source_file_content'] = source_stack.file_content
                result['source_details'] = source_stack.details
        
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
                    ('environment_id', '=', wizard.target_environment_id.id),
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
            # Determine the appropriate content and build method
            source_content = self.source_stack_id.content or self.source_stack_id.file_content or ''
            
            # Ensure we have content for web_editor method
            if not source_content:
                raise UserError(_("Source stack has no content to migrate. Cannot create stack without compose content."))
            
            # Handle dependencies if required
            processed_content = source_content
            if self.handle_dependencies in ['create_missing', 'abort']:
                _logger.info(f"Starting dependency analysis for stack migration. Handle mode: {self.handle_dependencies}")
                processed_content = self._handle_stack_dependencies(source_content)
                _logger.info("Dependency analysis completed successfully")
            
            # Emergency fallback: Create traefik-net if it doesn't exist (common network issue)
            if 'traefik-net' in source_content and self.handle_dependencies == 'create_missing':
                _logger.info("Detected traefik-net reference, ensuring it exists")
                self._create_missing_networks(['traefik-net'])
            
            # Prepare stack data for creation
            stack_vals = {
                'name': self.new_stack_name,
                'server_id': self.target_environment_id.server_id.id,
                'environment_id': self.target_environment_id.id,  # Use Odoo environment record ID, not Portainer ID
                'content': processed_content,
                'build_method': 'web_editor',  # Always use web_editor for migrations
                'type': self.source_stack_id.type,
                'status': '0',  # Unknown status initially
                'stack_id': 0,  # Will be set by create method after API call
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

    def _handle_stack_dependencies(self, stack_content):
        """Analyze and handle stack dependencies like external networks"""
        import yaml
        import re
        import logging
        _logger = logging.getLogger(__name__)
        
        try:
            # Parse docker-compose content
            if not stack_content.strip():
                return stack_content
                
            # Try to parse as YAML
            try:
                compose_data = yaml.safe_load(stack_content)
            except yaml.YAMLError:
                _logger.warning("Could not parse compose content as YAML, skipping dependency analysis")
                return stack_content
            
            if not isinstance(compose_data, dict):
                return stack_content
            
            # Extract external networks with better detection
            external_networks = []
            networks_section = compose_data.get('networks', {})
            
            # Check explicitly declared external networks
            for network_name, network_config in networks_section.items():
                if isinstance(network_config, dict) and network_config.get('external'):
                    external_networks.append(network_name)
                elif network_config is True or network_config == 'external':
                    # Handle shorthand external: true
                    external_networks.append(network_name)
            
            # Also check for external networks referenced in services
            services_section = compose_data.get('services', {})
            for service_name, service_config in services_section.items():
                if isinstance(service_config, dict):
                    service_networks = service_config.get('networks', [])
                    if isinstance(service_networks, list):
                        for network in service_networks:
                            if isinstance(network, str) and network not in networks_section:
                                # This might be an external network referenced without declaration
                                external_networks.append(network)
                    elif isinstance(service_networks, dict):
                        # Handle networks defined as dict with aliases
                        for network_name in service_networks.keys():
                            if network_name not in networks_section:
                                external_networks.append(network_name)
            
            _logger.info(f"Raw compose data networks section: {networks_section}")
            _logger.info(f"Detected external networks: {external_networks}")
            
            external_networks = list(set(external_networks))  # Remove duplicates
            
            if external_networks:
                _logger.info(f"Found external networks: {external_networks}")
                
                if self.handle_dependencies == 'abort':
                    raise UserError(_("Stack migration aborted: External networks found: %s. These networks don't exist in the target environment.") % ', '.join(external_networks))
                
                elif self.handle_dependencies == 'create_missing':
                    # Create missing networks in target environment
                    self._create_missing_networks(external_networks)
                    
            return stack_content
            
        except Exception as e:
            _logger.error(f"Error analyzing stack dependencies: {str(e)}")
            if self.handle_dependencies == 'abort':
                raise UserError(_("Failed to analyze stack dependencies: %s") % str(e))
            return stack_content
    
    def _create_missing_networks(self, network_names):
        """Create missing networks in the target environment"""
        import logging
        _logger = logging.getLogger(__name__)
        
        try:
            # Get existing networks in target environment
            existing_networks = self.env['j_portainer.network'].search([
                ('server_id', '=', self.target_environment_id.server_id.id),
                ('environment_id', '=', self.target_environment_id.id)
            ])
            
            existing_network_names = set(existing_networks.mapped('name'))
            
            for network_name in network_names:
                if network_name not in existing_network_names:
                    try:
                        _logger.info(f"Creating missing network: {network_name}")
                        
                        # Create network via Docker API (direct endpoint)
                        network_config = {
                            'Name': network_name,
                            'Driver': 'bridge',
                            'CheckDuplicate': True,
                            'Labels': {
                                'created_by': 'odoo_migration_wizard',
                                'migrated_from': self.source_stack_id.environment_id.name
                            },
                            'IPAM': {
                                'Driver': 'default'
                            }
                        }
                        
                        response = self.target_environment_id.server_id._make_api_request(
                            f'/api/endpoints/{self.target_environment_id.environment_id}/docker/networks',
                            method='POST',
                            data=network_config
                        )
                        
                        if response.status_code in [200, 201]:
                            _logger.info(f"Successfully created network: {network_name}")
                            
                            # Wait a moment for network to be fully registered
                            import time
                            time.sleep(2)
                            
                            # Verify network was created by checking Docker API
                            try:
                                check_response = self.target_environment_id.server_id._make_api_request(
                                    f'/api/endpoints/{self.target_environment_id.environment_id}/docker/networks',
                                    method='GET'
                                )
                                if check_response.status_code == 200:
                                    networks = check_response.json()
                                    network_exists = any(net.get('Name') == network_name for net in networks)
                                    if not network_exists:
                                        raise UserError(_("Network '%s' was created but not found in Docker. Please try again.") % network_name)
                                    _logger.info(f"Verified network {network_name} exists in Docker")
                            except Exception as verify_error:
                                _logger.warning(f"Could not verify network creation: {verify_error}")
                            
                            # Sync the network to Odoo to ensure it's available
                            try:
                                self.target_environment_id.sync_networks()
                            except:
                                pass  # Continue even if sync fails
                                
                        else:
                            _logger.warning(f"Failed to create network {network_name}: {response.text}")
                            # For critical networks, we might want to fail the migration
                            if self.handle_dependencies == 'create_missing':
                                raise UserError(_("Failed to create required network '%s': %s") % (network_name, response.text))
                            
                    except Exception as network_error:
                        _logger.warning(f"Could not create network {network_name}: {str(network_error)}")
                        if self.handle_dependencies == 'create_missing':
                            raise UserError(_("Failed to create required network '%s': %s") % (network_name, str(network_error)))
                        # Continue with other networks for ignore mode
                        continue
                        
        except Exception as e:
            _logger.error(f"Error creating missing networks: {str(e)}")
            # Don't fail the migration for network creation issues
            pass

    def action_cancel(self):
        """Cancel wizard"""
        return {'type': 'ir.actions.act_window_close'}