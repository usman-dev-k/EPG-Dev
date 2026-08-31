# -*- coding: utf-8 -*-
{
    'name': 'SaaS Admin Dashboard',
    'version': '1.0',
    'category': 'SaaS',
    'summary': 'Admin dashboard for tenant management and monitoring',
    'description': """
        SaaS Admin Dashboard
        ====================
        
        Features:
        * Tenant overview and monitoring
        * Manual tenant deletion wizard
        * Usage statistics
        * Subscription analytics
        * Audit logs
    """,
    'author': 'Your Company',
    'website': 'https://abc.com',
    'depends': ['saas_management', 'saas_provisioning'],
    'data': [
        'security/ir.model.access.csv',
        'views/saas_dashboard_views.xml',
        'views/menu.xml',
        'wizard/tenant_deletion_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
