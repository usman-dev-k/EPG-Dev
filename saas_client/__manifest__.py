# -*- coding: utf-8 -*-
{
    'name': 'SaaS Client Agent',
    'version': '1.0',
    'category': 'SaaS',
    'summary': 'Enforces resource limits on tenant databases',
    'description': """
        SaaS Client Agent
        =================
        
        Installed on Tenant Databases to:
        * Enforce User Limits (saas.max_users)
        * Enforce Storage Limits (saas.max_storage_mb)
        
        This module reads limits from System Parameters (ir.config_parameter), 
        which are managed by the SaaS Manager.
    """,
    'author': 'Your Company',
    'website': 'https://abc.com',
    'depends': ['base', 'odoo_url_replacer', 'sales_team', 'web', 'portal', 'mail', 'account', 'l10n_es', 'account_bank_sync_yapily'],
    'data': [
        'views/res_config_settings_views.xml',
        'views/login_templates.xml',
        'views/onboarding_templates.xml',
        'views/portal_templates.xml',
        'views/res_company_views.xml',
        'views/res_users_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'saas_client/static/src/suggestion_box/suggestion_box.js',
            'saas_client/static/src/suggestion_box/suggestion_box.xml',
            'saas_client/static/src/suggestion_box/suggestion_box.scss',
            'saas_client/static/src/video_tutorial/video_tutorial.js',
            'saas_client/static/src/video_tutorial/video_tutorial.xml',
            'saas_client/static/src/video_tutorial/video_tutorial.scss',
            'saas_client/static/src/expiration_warning/expiration_warning.js',
            'saas_client/static/src/expiration_warning/expiration_warning.xml',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
