# -*- coding: utf-8 -*-
{
    'name': 'SaaS Management',
    'version': '1.0',
    'category': 'SaaS',
    'summary': 'Multi-tenant SaaS platform management with subscription plans and automated provisioning',
    'description': """
        SaaS Management Module
        ======================
        
        Core module for managing multi-tenant SaaS platform:
        * Subscription plan management with pricing tiers
        * Early adopter program (first 1000 customers)
        * Promotional code system
        * Tenant subscription tracking
        * Automated tenant lifecycle management
        * Grace period and deletion workflows
    """,
    'author': 'Your Company',
    'website': 'https://abc.com',
    'depends': ['base', 'sale', 'website_sale', 'payment'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/saas_plan_data.xml',
        'data/cron_jobs.xml',
        'data/mail_template.xml',
        'views/menu.xml',
        # 'views/res_config_settings_views.xml',
        'views/saas_plan_views.xml',
        'views/saas_subscription_views.xml',
        'views/saas_addon_views.xml',
        'views/saas_promo_code_views.xml',
        'views/saas_suggestion_views.xml',
        'views/saas_subscription_portal_templates.xml',
        'wizards/saas_upgrade_wizard.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
