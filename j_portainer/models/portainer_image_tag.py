#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
import random

class PortainerImageTag(models.Model):
    _name = 'j_portainer.image.tag'
    _description = 'Portainer Image Tag'
    _rec_name = 'display_name'
    
    repository = fields.Char('Repository', required=True, index=True)
    tag = fields.Char('Tag', required=True, index=True)
    display_name = fields.Char('Display Name', compute='_compute_display_name', store=True, index=True)
    image_id = fields.Many2one('j_portainer.image', string='Image', required=True)
    color = fields.Integer('Color Index', default=lambda self: random.randint(1, 11))
    
    _sql_constraints = [
        ('tag_unique', 'unique(image_id, repository, tag)', 'Tag must be unique per repository within an image!')
    ]
    
    @api.depends('repository', 'tag')
    def _compute_display_name(self):
        """Compute display name based on repository and tag"""
        for tag in self:
            tag.display_name = f"{tag.repository}:{tag.tag}"
            
    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        """Override name_search to search in both repository and tag fields"""
        args = args or []
        domain = []
        
        if name:
            domain = ['|', '|',
                ('display_name', operator, name),
                ('repository', operator, name),
                ('tag', operator, name)]
                
        return self.search(domain + args, limit=limit).name_get()