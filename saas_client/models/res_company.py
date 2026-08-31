# -*- coding: utf-8 -*-

from odoo import models, fields

class ResCompany(models.Model):
    _inherit = 'res.company'

    saas_onboarding_done = fields.Boolean(
        string="SaaS Onboarding Done",
        default=False,
        help="Technical field to track if the client has completed the initial setup wizard."
    )
    
    # Onboarding Data Fields
    saas_client_type = fields.Selection([
        ('self_employed', 'Self-employed / Autónomo'),
        ('company', 'Company / Empresa')
    ], string="Type of Client")
    
    saas_commercial_name = fields.Char(string="Commercial Name")
    
    saas_activity_type = fields.Selection([
        ('services', 'Services'),
        ('consulting', 'Consulting'),
        ('accounting', 'Accounting/Tax firm'),
        ('construction', 'Construction'),
        ('real_estate', 'Real estate'),
        ('transport', 'Transport'),
        ('commerce', 'Commerce'),
        ('other', 'Other')
    ], string="Activity Type")
    
    saas_main_objective = fields.Selection([
        ('more_clients', 'Get more clients'),
        ('save_time', 'Save time'),
        ('automate', 'Automate tasks'),
        ('manage_invoicing', 'Manage invoicing'),
        ('organize_docs', 'Organize documentation')
    ], string="Main Objective")
    
    saas_user_count_expected = fields.Selection([
        ('1', '1'),
        ('2_5', '2-5'),
        ('6_10', '6-10'),
        ('10_plus', 'More than 10')
    ], string="Expected Users")
    
    saas_use_quotations = fields.Boolean("Uses Quotations")
    saas_use_sales_followup = fields.Boolean("Does Sales Follow-up")
    
    saas_issue_invoices = fields.Boolean("Issues Invoices")
    saas_record_supplier_invoices = fields.Boolean("Records Supplier Invoices")
    saas_use_accounting = fields.Boolean("Uses Integrated Accounting")
    saas_accounting_handler = fields.Selection([
        ('myself', 'Myself'),
        ('firm', 'My accounting firm'),
        ('both', 'Both')
    ], string="Who handles accounting")
    
    saas_wants_ai = fields.Boolean("Wants AI Assistant")
    
    saas_import_strategy = fields.Selection([
        ('excel', 'Import Excel'),
        ('scratch', 'Start from scratch')
    ], string="Import Strategy")
