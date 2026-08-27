# -*- coding: utf-8 -*-
{
    'name': 'EPG CRM POS Theme',
    'version': '1.0',
    'category': 'Sales/Point of Sale',
    'summary': 'Custom 4-zone UI and EPG CRM branding for the Point of Sale.',
    'description': """
        This module completely restyles the standard Odoo 18 Point of Sale.
        - Removes Odoo branding.
        - Implements the custom 4-zone layout (Entrada Inteligente, Ticket, Actions, Resumen).
        - Uses EPG CRM color schemes.
    """,
    'author': 'EPG CRM',
    'depends': ['point_of_sale', 'stock'],
    'data': [
        'views/res_config_settings_views.xml',
        'views/menu_icons.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'epg_pos_theme/static/src/css/pos_theme.scss',
            'epg_pos_theme/static/src/xml/pos_overrides.xml',
            'epg_pos_theme/static/src/css/hide_logo.scss',
            'epg_pos_theme/static/src/js/set_title.js',
        ],
        'point_of_sale.customer_display_assets': [
            'epg_pos_theme/static/src/css/hide_logo.scss',
        ],
        'point_of_sale.assets_customer_display': [
            'epg_pos_theme/static/src/css/hide_logo.scss',
        ],
        'web.assets_common': [
            'epg_pos_theme/static/src/css/hide_logo.scss',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
