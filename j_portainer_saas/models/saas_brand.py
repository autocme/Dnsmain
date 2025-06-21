#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class SaasBrand(models.Model):
    """
    SaaS Brand Model for J Portainer SaaS
    
    This model manages branding information for SaaS deployments.
    """
    
    _name = 'saas.brand'
    _description = 'SaaS Brand Management'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sb_name'
    _rec_name = 'sb_name'

    # ========================================================================
    # BASIC FIELDS
    # ========================================================================

    sb_name = fields.Char(
        string='Name',
        required=True,
        tracking=True,
        help='Brand name for SaaS deployments (e.g., obill)'
    )
    
    sb_default_logo_module = fields.Char(
        string='Default Logo Module',
        tracking=True,
        help='Module name containing the default logo (e.g., saas_branding)'
    )
    
    sb_title = fields.Char(
        string='Title',
        tracking=True,
        help='Display title used in web applications (e.g., obill)'
    )
    
    sb_favicon_url = fields.Char(
        string='Favicon URL',
        tracking=True,
        help='URL to the favicon icon file (e.g., https://www.obill.it/favicon.ico)'
    )
    
    sb_website = fields.Char(
        string='Website',
        tracking=True,
        help='Main website URL (e.g., https://www.obill.it)'
    )
    
    sb_primary_color = fields.Char(
        string='Primary Color',
        tracking=True,
        help='Primary brand color (hex code)'
    )
    
    sb_secondary_color = fields.Char(
        string='Secondary Color',
        tracking=True,
        help='Secondary brand color (hex code)'
    )
    
    sb_brand_slogan = fields.Char(
        string='Brand Slogan',
        tracking=True,
        help='Marketing slogan or tagline for the brand'
    )
    
    sb_brand_logo_link = fields.Char(
        string='Brand Logo Link',
        tracking=True,
        help='URL to the brand logo image file'
    )
    
    sb_brand_image = fields.Binary(
        string='Brand Image',
        tracking=True,
        help='Upload brand logo/image file'
    )
    
    sb_docs_website = fields.Char(
        string='Docs Website',
        tracking=True,
        help='URL to documentation website (e.g., https://www.jaah.it/documentation/)'
    )
    
    sb_warranty = fields.Boolean(
        string='Warranty',
        default=False,
        tracking=True,
        help='Indicates if warranty is provided for this brand'
    )


    
    sb_company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
        help='Company that owns this brand configuration'
    )
    
    sb_active = fields.Boolean(
        string='Active',
        default=True,
        tracking=True,
        help='Uncheck to hide this brand without deleting it'
    )

    # ========================================================================
    # CONSTRAINTS
    # ========================================================================

    _sql_constraints = [
        (
            'unique_brand_name_company',
            'UNIQUE(sb_name, sb_company_id)',
            'Brand name must be unique per company.'
        ),
    ]

    # ========================================================================
    # CRUD METHODS
    # ========================================================================

