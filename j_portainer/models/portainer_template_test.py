#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _

class PortainerTemplateTest(models.Model):
    _name = 'j_portainer.template.test'
    _description = 'Portainer Template Test'
    
    name = fields.Char('Name', required=True)
    description = fields.Text('Description')
    server_id = fields.Many2one('j_portainer.server', string='Server', required=True)