# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request

class DockerController(http.Controller):
    
    @http.route(['/docker/container/logs/<int:container_id>'], type='http', auth='user')
    def container_logs(self, container_id, **kw):
        """Display container logs in a dedicated page"""
        container = request.env['j_docker.docker_container'].browse(container_id)
        if not container.exists():
            return request.not_found()
            
        try:
            logs = container.get_logs(tail=500)
            return request.render('j_docker.container_logs_template', {
                'container': container,
                'logs': logs
            })
        except Exception as e:
            return request.render('j_docker.error_template', {
                'error': str(e)
            })