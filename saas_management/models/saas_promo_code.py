# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from datetime import datetime, timedelta
import secrets
import string
import logging

_logger = logging.getLogger(__name__)


class SaaSPromoCode(models.Model):
    _name = 'saas.promo.code'
    _description = 'SaaS Promotional Code'
    _order = 'create_date desc'

    name = fields.Char(string='Promo Code Name', required=True)
    code = fields.Char(string='Code', copy=False, index=True, help='Leave empty to auto-generate')
    active = fields.Boolean(default=True)
    
    # Type and Purpose
    code_type = fields.Selection([
        ('early_adopter', 'Early Adopter'),
    ], string='Type', required=True, default='early_adopter')
    
    description = fields.Text(string='Description')
    
    # Early Adopter Override
    grant_early_adopter = fields.Boolean(
        string='Grant Early Adopter Status',
        default=True,
        help='Allow early adopter pricing even after 1000 limit reached'
    )
    
    # Discount Settings
    discount_percentage = fields.Float(string='Discount %', digits=(5, 2))
    discount_amount = fields.Float(string='Discount Amount (€)', digits=(10, 2))
    
    # Usage Limits
    max_uses = fields.Integer(string='Maximum Uses', default=1, help='0 = unlimited')
    current_uses = fields.Integer(string='Current Uses', compute='_compute_usage', store=True)
    remaining_uses = fields.Integer(string='Remaining Uses', compute='_compute_usage', store=True)
    
    # Validity Period
    valid_from = fields.Datetime(string='Valid From', default=fields.Datetime.now)
    valid_until = fields.Datetime(string='Valid Until')
    
    # Usage Tracking
    usage_ids = fields.One2many('saas.promo.code.usage', 'promo_code_id', string='Usage History')
    
    # Created By
    created_by_id = fields.Many2one('res.users', string='Created By', default=lambda self: self.env.user, readonly=True)
    
    _sql_constraints = [
        ('code_unique', 'unique(code)', 'Promo code must be unique!')
    ]
    
    @api.depends('usage_ids')
    def _compute_usage(self):
        for promo in self:
            promo.current_uses = len(promo.usage_ids)
            if promo.max_uses > 0:
                promo.remaining_uses = max(0, promo.max_uses - promo.current_uses)
            else:
                promo.remaining_uses = -1  # Unlimited
    
    @api.model_create_multi
    def create(self, vals_list):
        # Auto-generate code if not provided
        for vals in vals_list:
            if not vals.get('code'):
                vals['code'] = self._generate_code()
            else:
                vals['code'] = vals['code'].upper()
        return super(SaaSPromoCode, self).create(vals_list)
    
    def write(self, vals):
        if 'code' in vals:
            vals['code'] = vals['code'].upper()
        return super(SaaSPromoCode, self).write(vals)
    
    @api.model
    def _generate_code(self, length=8):
        """Generate random promo code"""
        characters = string.ascii_uppercase + string.digits
        code = ''.join(secrets.choice(characters) for _ in range(length))
        
        # Ensure uniqueness
        while self.search([('code', '=', code)], limit=1):
            code = ''.join(secrets.choice(characters) for _ in range(length))
        
        return code
    
    def can_use(self):
        """Check if promo code can be used"""
        self.ensure_one()
        
        if not self.active:
            return False
        
        # Check validity period
        now = fields.Datetime.now()
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_until and now > self.valid_until:
            return False
        
        # Check usage limit
        if self.max_uses > 0 and self.current_uses >= self.max_uses:
            return False
        
        return True
    
    def use_code(self, partner_id, subscription_id=None):
        """Record promo code usage"""
        self.ensure_one()
        
        if not self.can_use():
            raise UserError(_('This promo code cannot be used'))
        
        # Create usage record
        self.env['saas.promo.code.usage'].create({
            'promo_code_id': self.id,
            'partner_id': partner_id,
            'subscription_id': subscription_id,
            'used_date': fields.Datetime.now()
        })
        
        _logger.info(f'Promo code {self.code} used by partner {partner_id}')
        
        return True
    
    def action_view_usage(self):
        """View usage history"""
        return {
            'name': _('Usage History'),
            'type': 'ir.actions.act_window',
            'res_model': 'saas.promo.code.usage',
            'view_mode': 'list,form',
            'domain': [('promo_code_id', '=', self.id)],
        }


class SaaSPromoCodeUsage(models.Model):
    _name = 'saas.promo.code.usage'
    _description = 'Promo Code Usage History'
    _order = 'used_date desc'

    promo_code_id = fields.Many2one('saas.promo.code', string='Promo Code', required=True, ondelete='cascade')
    partner_id = fields.Many2one('res.partner', string='Customer', required=True)
    subscription_id = fields.Many2one('saas.subscription', string='Subscription')
    used_date = fields.Datetime(string='Used Date', required=True, default=fields.Datetime.now)
    
    # Audit
    ip_address = fields.Char(string='IP Address')
    user_agent = fields.Char(string='User Agent')
