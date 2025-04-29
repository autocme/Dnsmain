#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)

class PortainerTemplateCategory(models.Model):
    _name = 'j_portainer.template.category'
    _description = 'Portainer Template Category'
    _order = 'name'
    
    name = fields.Char('Category Name', required=True)
    
    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'Category name must be unique')
    ]