import json
import logging
import werkzeug.exceptions
from werkzeug.exceptions import BadRequest

from odoo import http, _
from odoo.http import request
from odoo.exceptions import AccessError, ValidationError, UserError

_logger = logging.getLogger(__name__)

class DockerController(http.Controller):
    @http.route('/j_docker/dashboard', type='http', auth='user', website=True)
    def docker_dashboard(self, **kw):
        """Render the Docker dashboard view"""
        servers = request.env['docker.server'].search([])
        values = {
            'servers': servers,
            'page_name': 'docker_dashboard',
            'containers_count': request.env['docker.container'].search_count([]),
            'images_count': request.env['docker.image'].search_count([]),
        }
        return request.render('j_docker.dashboard_template', values)
    
    @http.route('/j_docker/server/<int:server_id>', type='http', auth='user', website=True)
    def docker_server_details(self, server_id, **kw):
        """Render the Docker server detail view"""
        server = request.env['docker.server'].browse(server_id)
        if not server.exists():
            return werkzeug.exceptions.NotFound()
            
        values = {
            'server': server,
            'page_name': 'server_details',
        }
        return request.render('j_docker.server_details_template', values)
    
    @http.route('/j_docker/api/servers', type='json', auth='user')
    def get_servers(self, **kw):
        """API endpoint to get all servers"""
        try:
            servers = request.env['docker.server'].search([])
            server_data = []
            
            for server in servers:
                server_data.append({
                    'id': server.id,
                    'name': server.name,
                    'status': server.server_status,
                    'containers': server.container_count,
                    'running_containers': server.running_container_count,
                    'images': server.image_count,
                    'cpu_usage': server.cpu_usage,
                    'memory_usage': server.memory_usage,
                    'disk_usage': server.disk_usage,
                })
                
            return {'status': 'success', 'data': server_data}
        except Exception as e:
            _logger.exception("Error fetching servers: %s", str(e))
            return {'status': 'error', 'error': str(e)}
    
    @http.route('/j_docker/api/server/<int:server_id>/refresh', type='json', auth='user')
    def refresh_server(self, server_id, **kw):
        """API endpoint to refresh server details"""
        try:
            server = request.env['docker.server'].browse(server_id)
            if not server.exists():
                return {'status': 'error', 'error': 'Server not found'}
                
            server._check_connection()
            server._refresh_server_info()
            
            return {
                'status': 'success',
                'data': {
                    'id': server.id,
                    'name': server.name,
                    'status': server.server_status,
                    'containers': server.container_count,
                    'running_containers': server.running_container_count,
                    'images': server.image_count,
                    'cpu_usage': server.cpu_usage,
                    'memory_usage': server.memory_usage,
                    'disk_usage': server.disk_usage,
                }
            }
        except Exception as e:
            _logger.exception("Error refreshing server: %s", str(e))
            return {'status': 'error', 'error': str(e)}
    
    @http.route('/j_docker/api/server/<int:server_id>/containers', type='json', auth='user')
    def get_server_containers(self, server_id, **kw):
        """API endpoint to get containers for a server"""
        try:
            server = request.env['docker.server'].browse(server_id)
            if not server.exists():
                return {'status': 'error', 'error': 'Server not found'}
                
            containers = request.env['docker.container'].search([
                ('server_id', '=', server_id),
                ('active', '=', True)
            ])
            
            container_data = []
            for container in containers:
                container_data.append({
                    'id': container.id,
                    'name': container.name,
                    'docker_id': container.docker_id,
                    'image': container.image,
                    'status': container.status,
                    'status_text': container.status_text,
                    'ports': container.ports,
                    'cpu_usage': container.cpu_usage,
                    'memory_usage': container.memory_usage,
                })
                
            return {'status': 'success', 'data': container_data}
        except Exception as e:
            _logger.exception("Error fetching containers: %s", str(e))
            return {'status': 'error', 'error': str(e)}
    
    @http.route('/j_docker/api/container/<int:container_id>/action', type='json', auth='user')
    def container_action(self, container_id, action, **kw):
        """API endpoint to perform actions on a container"""
        try:
            container = request.env['docker.container'].browse(container_id)
            if not container.exists():
                return {'status': 'error', 'error': 'Container not found'}
                
            result = {}
            if action == 'start':
                container.action_start()
                result = {'status': 'success', 'message': f'Container {container.name} started'}
            elif action == 'stop':
                container.action_stop()
                result = {'status': 'success', 'message': f'Container {container.name} stopped'}
            elif action == 'restart':
                container.action_restart()
                result = {'status': 'success', 'message': f'Container {container.name} restarted'}
            elif action == 'remove':
                container.action_remove()
                result = {'status': 'success', 'message': f'Container {container.name} removed'}
            elif action == 'refresh':
                container._update_container_details()
                result = {'status': 'success', 'message': f'Container {container.name} refreshed'}
            else:
                result = {'status': 'error', 'error': f'Unknown action: {action}'}
                
            return result
        except Exception as e:
            _logger.exception("Error performing container action: %s", str(e))
            return {'status': 'error', 'error': str(e)}
    
    @http.route('/j_docker/api/server/<int:server_id>/images', type='json', auth='user')
    def get_server_images(self, server_id, **kw):
        """API endpoint to get images for a server"""
        try:
            server = request.env['docker.server'].browse(server_id)
            if not server.exists():
                return {'status': 'error', 'error': 'Server not found'}
                
            images = request.env['docker.image'].search([
                ('server_id', '=', server_id),
                ('active', '=', True)
            ])
            
            image_data = []
            for image in images:
                image_data.append({
                    'id': image.id,
                    'name': image.name,
                    'docker_id': image.docker_id,
                    'repository': image.repository,
                    'tag': image.tag,
                    'size': image.size,
                    'used_by_containers': image.used_by_containers,
                    'dangling': image.dangling,
                })
                
            return {'status': 'success', 'data': image_data}
        except Exception as e:
            _logger.exception("Error fetching images: %s", str(e))
            return {'status': 'error', 'error': str(e)}
    
    @http.route('/j_docker/api/server/<int:server_id>/exec', type='json', auth='user')
    def execute_command(self, server_id, command, **kw):
        """API endpoint to execute a command on a server"""
        try:
            server = request.env['docker.server'].browse(server_id)
            if not server.exists():
                return {'status': 'error', 'error': 'Server not found'}
                
            if not server.ssh_client_id:
                return {'status': 'error', 'error': 'Server has no SSH client configured'}
                
            # Execute the command
            ssh_client = server.ssh_client_id
            result = ssh_client.exec_command(command)
            
            # Log the command execution
            server._create_log_entry('info', f'API executed command: {command}')
            
            return {'status': 'success', 'result': result}
        except Exception as e:
            _logger.exception("Error executing command: %s", str(e))
            return {'status': 'error', 'error': str(e)}
    
    @http.route('/j_docker/api/logs', type='json', auth='user')
    def get_logs(self, limit=100, level=None, entity_type=None, entity_id=None, **kw):
        """API endpoint to get logs with filtering"""
        try:
            domain = []
            
            # Filter by log level
            if level:
                domain.append(('level', '=', level))
                
            # Filter by entity type and ID
            if entity_type and entity_id:
                if entity_type == 'server':
                    domain.append(('server_id', '=', int(entity_id)))
                elif entity_type == 'container':
                    domain.append(('container_id', '=', int(entity_id)))
                elif entity_type == 'image':
                    domain.append(('image_id', '=', int(entity_id)))
                elif entity_type == 'network':
                    domain.append(('network_id', '=', int(entity_id)))
                elif entity_type == 'volume':
                    domain.append(('volume_id', '=', int(entity_id)))
                elif entity_type == 'task':
                    domain.append(('task_id', '=', int(entity_id)))
            
            # Get logs
            logs = request.env['docker.logs'].search(domain, limit=limit, order='create_date desc')
            
            log_data = []
            for log in logs:
                log_data.append({
                    'id': log.id,
                    'message': log.name,
                    'level': log.level,
                    'user': log.user_id.name,
                    'date': log.create_date,
                    'server_id': log.server_id.id if log.server_id else False,
                    'server_name': log.server_id.name if log.server_id else False,
                    'container_id': log.container_id.id if log.container_id else False,
                    'container_name': log.container_id.name if log.container_id else False,
                    'image_id': log.image_id.id if log.image_id else False,
                    'image_name': log.image_id.name if log.image_id else False,
                    'network_id': log.network_id.id if log.network_id else False,
                    'network_name': log.network_id.name if log.network_id else False,
                    'volume_id': log.volume_id.id if log.volume_id else False,
                    'volume_name': log.volume_id.name if log.volume_id else False,
                    'task_id': log.task_id.id if log.task_id else False,
                    'task_name': log.task_id.name if log.task_id else False,
                })
                
            return {'status': 'success', 'data': log_data}
        except Exception as e:
            _logger.exception("Error fetching logs: %s", str(e))
            return {'status': 'error', 'error': str(e)}