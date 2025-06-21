#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging
import re

_logger = logging.getLogger(__name__)


class SystemType(models.Model):

    _name = 'system.type'
    _description = 'System Type'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'st_sequence'
    _rec_name = 'st_complete_name'

    # ========================================================================
    # FIELDS
    # ========================================================================


    st_sequence = fields.Char(
        string='Sequence',
        readonly=True,
        copy=False,
        default=lambda self: _('New'),
        tracking=True,
        help='Auto-generated sequence code for package ordering (e.g., ST00001)'
    )
    st_name = fields.Char(
        string='Name',
        required=True,
        translate=True,
        tracking=True,
        help='Display name of the SaaS package'
    )
    st_complete_name = fields.Char(string='Rec Name', compute='_compute_title_name', store=True, tracking=True)
    st_company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company, tracking=True)

    @api.depends('st_name', 'st_sequence')
    def _compute_title_name(self):
        for rec in self:
            rec.title_name = "%s - %s" % (rec.st_sequence or '', rec.st_name or '')

    st_environment_ids = fields.One2many('j_portainer.environment', 'system_type_id', string='Environments', tracking=True)
    st_environment_count = fields.Integer('Environments', compute='_compute_environment_count', )

    def _compute_environment_count(self):
        if self:
            for rec in self:
                if rec.st_environment_ids:
                    rec.st_environment_count = len(self.st_environment_ids)
                else:
                    rec.st_environment_count = 0


    st_domain_id = fields.Many2many('dns.domain', string='Domain', tracking=True)

    st_stack_count = fields.Integer('Stacks', compute='_compute_st_stack_count', )

    def _compute_st_stack_count(self):
        for rec in self:
            count = 0
            for env in rec.st_environment_ids:
                count += len(env.stack_count)
            rec.st_stack_count = count

    st_send_email_on_stack_create = fields.Boolean(string='Send Email on stack create', default=True, tracking=True)

    st_saas_package_ids = fields.One2many('saas.package', 'pkg_system_type_id', string='Packages', tracking=True)

    st_saas_package_count = fields.Integer('Packages', compute='_compute_package_count', )

    def _compute_package_count(self):
        if self:
            for rec in self:
                if rec.saas_backage_ids:
                    rec.st_saas_package_count = len(self.st_saas_package_ids)
                else:
                    rec.st_saas_package_count = 0

    # ========================================================================
    # CONSTRAINTS
    # ========================================================================

    _sql_constraints = [
        (
            'unique_system_type_sequence',
            'UNIQUE(st_sequence)',
            'System Type sequence must be unique.'
        ),


    ]
