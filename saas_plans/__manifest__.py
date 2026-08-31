# -*- coding: utf-8 -*-
{
    'name': 'SaaS Website Plans',
    'version': '1.0',
    'category': 'Website/Website',
    'summary': 'Display SaaS plans on website and handle payment integration',
    'description': """
        SaaS Website Plans Module
        ==========================
        
        Features:
        * Display subscription plans on website
        * Collect company name before payment
        * Integrate with Redsys payment gateway (custom wrapper)
        * Auto-provision tenant after successful payment
        * Handle payment webhooks
    """,
    'author': 'Your Company',
    'website': 'https://abc.com',
    'depends': [
        'website',
        'website_sale',
        'saas_management',
        'saas_provisioning',
        'payment',  # System's payment module
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/saas_plan_website_templates.xml',
        'views/saas_portal_templates.xml',
        'views/checkout_templates.xml',
        'data/product_data.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'saas_plans/static/src/css/saas_plans.css',
            'saas_plans/static/src/js/saas_checkout.js',
            'saas_plans/static/src/js/promo_code.js',
            'saas_plans/static/src/js/saas_registration.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
