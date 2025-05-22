#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _

class PortainerImageTag(models.Model):
    _name = 'j_portainer.image.tag'
    _description = 'Portainer Image Tag'
    _rec_name = 'display_name'
    
    repository = fields.Char('Repository', required=True)
    tag = fields.Char('Tag', required=True)
    display_name = fields.Char('Display Name', compute='_compute_display_name', store=True)
    image_id = fields.Many2one('j_portainer.image', string='Image', required=True, ondelete='cascade')
    
    @api.depends('repository', 'tag')
    def _compute_display_name(self):
        """Compute display name based on repository and tag"""
        for tag in self:
            tag.display_name = f"{tag.repository}:{tag.tag}"