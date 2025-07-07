# -*- coding: utf-8 -*-

from odoo import models, fields, api


class PackageFeatures(models.Model):
    _name = 'saas.package.features'
    _description = 'SaaS Package Features'
    _order = 'pf_sequence, id'

    pf_package_id = fields.Many2one(
        'saas.package',
        string='Package',
        required=True,
        ondelete='cascade'
    )
    pf_name = fields.Text(
        string='Feature Description',
        required=True,
        help='Description of the package feature'
    )
    pf_sequence = fields.Integer(
        string='Sequence',
        default=10,
        help='Sequence order of the feature'
    )