#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)

class PortainerGitCredentials(models.Model):
    _name = 'j_portainer.git.credentials'
    _description = 'Portainer Git Credentials'
    _order = 'name'
    
    name = fields.Char('Credential Name', required=True)
    username = fields.Char('Username', required=True)
    token = fields.Char('Personal Access Token/Password', required=True)
    server_id = fields.Many2one('j_portainer.server', string='Server', required=True)
    
    _sql_constraints = [
        ('name_server_uniq', 'unique(name, server_id)', 'Credential name must be unique per server!')
    ]