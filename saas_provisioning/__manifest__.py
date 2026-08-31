# -*- coding: utf-8 -*-
{
    'name': 'SaaS Provisioning',
    'version': '1.0',
    'category': 'SaaS',
    'summary': 'Automated tenant database provisioning and management',
    'description': """
        SaaS Provisioning Module
        =========================
        
        Automates tenant provisioning workflow:
        * Database creation (localhost and Docker compatible)
        * Module installation based on subscription plan
        * Subdomain assignment and tracking
        * Backup and deletion services
        * Integration with subscription lifecycle
    """,
    'author': 'Your Company',
    'website': 'https://abc.com',
    'depends': ['saas_management'],
    'data': [
        'security/ir.model.access.csv',
        'data/config_parameters.xml',
        'data/mail_template.xml',
        'data/invoice_automation.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
