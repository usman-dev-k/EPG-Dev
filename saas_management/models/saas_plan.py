# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class SaaSPlan(models.Model):
    _name = 'saas.plan'
    _description = 'SaaS Subscription Plan'
    _order = 'sequence, id'

    name = fields.Char(string='Plan Name', required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    
    # Plan Type
    plan_type = fields.Selection([
        ('crm_early', 'CRM Early Adopter'),
        ('crm_official', 'CRM Official'),
    ], string='Plan Type', required=True)
    
    
    # Pricing (excluding VAT)
    price_monthly = fields.Float(string='Monthly Price (€)', digits=(10, 2))
    price_annual = fields.Float(string='Annual Price (€)', digits=(10, 2))
    early_adopter_price = fields.Float(
        string='Early Adopter Equivalent (€/month)', 
        digits=(10, 2),
        help='Monthly equivalent price for early adopters (e.g. €29.90 for annual plan at €358/yr)'
    )
    
    # Billing
    billing_cycle = fields.Selection([
        ('monthly', 'Monthly'),
        ('annual', 'Annual'),
    ], string='Billing Cycle', required=True, default='monthly')

    
    # Limits and Quotas
    included_users = fields.Integer(string='Included Users', default=3)
    included_storage_gb = fields.Integer(string='Included Storage (GB)', default=3)
    
    # Modules to Install
    module_ids = fields.Many2many(
        'ir.module.module',
        'saas_plan_module_rel',
        'plan_id',
        'module_id',
        string='Modules to Install',
        domain=[('state', '=', 'installed')]
    )
    module_names = fields.Char(
        string='Module Technical Names',
        help='Comma-separated list of module technical names to install (e.g., crm,account)'
    )
    
    # Early Adopter Settings
    is_early_adopter = fields.Boolean(
        string='Early Adopter Plan',
        default=False,
        help='First 1000 customers get special pricing and benefits'
    )
    early_adopter_limit = fields.Integer(
        string='Early Adopter Limit',
        default=1000,
        help='Maximum number of early adopter subscriptions (global across all plans)'
    )
    early_adopter_count = fields.Integer(
        string='Early Adopter Count (Global)',
        compute='_compute_early_adopter_count',
        store=True
    )
    early_adopter_available = fields.Integer(
        string='Early Adopter Slots Available',
        compute='_compute_early_adopter_count',
        store=True
    )
    
    # Product Link (for eCommerce)
    product_id = fields.Many2one(
        'product.product',
        string='Linked Product',
        help='Product in shop that represents this plan'
    )
    
    # Subscriptions
    subscription_ids = fields.One2many(
        'saas.subscription',
        'plan_id',
        string='Subscriptions'
    )
    subscription_count = fields.Integer(
        string='Total Subscriptions',
        compute='_compute_subscription_count'
    )
    active_subscription_count = fields.Integer(
        string='Active Subscriptions',
        compute='_compute_subscription_count'
    )
    
    # Description
    description = fields.Html(string='Description')
    features = fields.Text(string='Features', help='One feature per line')
    
    @api.depends('subscription_ids', 'subscription_ids.is_early_adopter', 'subscription_ids.state')
    def _compute_early_adopter_count(self):
        """Compute GLOBAL early adopter count across ALL plans"""
        # Get total count of all early adopter subscriptions globally
        global_count = self.env['saas.subscription'].search_count([
            ('is_early_adopter', '=', True),
            ('state', 'in', ['active', 'pending', 'grace_period'])
        ])
        for plan in self:
            plan.early_adopter_count = global_count
            plan.early_adopter_available = max(0, plan.early_adopter_limit - global_count)
    
    @api.depends('subscription_ids', 'subscription_ids.state')
    def _compute_subscription_count(self):
        for plan in self:
            plan.subscription_count = len(plan.subscription_ids)
            plan.active_subscription_count = len(
                plan.subscription_ids.filtered(lambda s: s.state == 'active')
            )
    
    @api.constrains('price_monthly', 'price_annual', 'billing_cycle')
    def _check_pricing(self):
        for plan in self:
            if plan.billing_cycle == 'monthly' and plan.price_monthly <= 0:
                raise ValidationError(_('Monthly price must be greater than 0 for monthly billing'))
            if plan.billing_cycle == 'annual' and plan.price_annual <= 0:
                raise ValidationError(_('Annual price must be greater than 0 for annual billing'))
    
    def action_view_subscriptions(self):
        """Open subscriptions for this plan"""
        return {
            'name': _('Subscriptions'),
            'type': 'ir.actions.act_window',
            'res_model': 'saas.subscription',
            'view_mode': 'list,form',
            'domain': [('plan_id', '=', self.id)],
            'context': {'default_plan_id': self.id}
        }
    
    def get_price(self, billing_cycle=None):
        """Get price for specified billing cycle"""
        self.ensure_one()
        cycle = billing_cycle or self.billing_cycle
        return self.price_annual if cycle == 'annual' else self.price_monthly
    
    def can_use_early_adopter(self):
        """Check if early adopter slots are available (global counter)"""
        self.ensure_one()
        # Use SQL for atomicity/speed
        self.env.cr.execute("""
            SELECT COUNT(*) 
            FROM saas_subscription 
            WHERE is_early_adopter = TRUE 
            AND state IN ('active', 'pending', 'grace_period')
        """)
        global_count = self.env.cr.fetchone()[0]
        return global_count < self.early_adopter_limit

    @api.model
    def get_global_early_adopter_count(self):
        """Get the global count of early adopter subscriptions"""
        self.env.cr.execute("""
            SELECT COUNT(*) 
            FROM saas_subscription 
            WHERE is_early_adopter = TRUE 
            AND state IN ('active', 'pending', 'grace_period')
        """)
        return self.env.cr.fetchone()[0]
