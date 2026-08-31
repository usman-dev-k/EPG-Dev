# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class SaaSAddon(models.Model):
    _name = 'saas.addon'
    _description = 'SaaS Subscription Add-on'
    _order = 'purchase_date desc, id desc'
    _inherit = ['mail.thread']

    # ─── Relations ────────────────────────────────────────────────────────────
    subscription_id = fields.Many2one(
        'saas.subscription',
        string='Subscription',
        required=True,
        ondelete='cascade',
        index=True,
        tracking=True,
    )

    product_id = fields.Many2one(
        'product.product',
        string='Linked Product',
        ondelete='restrict',
        help='The specific product SKU associated with this add-on.'
    )

    # ─── Type & Quantity ──────────────────────────────────────────────────────
    addon_type = fields.Selection([
        ('users', 'Extra Users'),
        ('storage', 'Extra Storage (GB)'),
    ], string='Add-on Type', required=True, tracking=True)

    quantity = fields.Integer(
        string='Quantity',
        required=True,
        default=1,
        help='Number of users OR number of GB depending on add-on type.',
    )

    # ─── Pricing ──────────────────────────────────────────────────────────────
    monthly_price = fields.Float(
        string='Monthly Price (€)',
        required=True,
        digits=(10, 2),
        help='Full monthly price per unit for this add-on.',
    )

    annual_price = fields.Float(
        string='Annual Price (€)',
        digits=(10, 2),
        help='Full annual price for this add-on package.',
    )

    total_monthly = fields.Float(
        string='Full Monthly Total (€)',
        compute='_compute_total_monthly',
        store=True,
        digits=(10, 2),
    )



    # ─── Dates ────────────────────────────────────────────────────────────────
    purchase_date = fields.Date(
        string='Purchase Date',
        required=True,
        default=fields.Date.today,
        readonly=True,
    )

    next_renewal_date = fields.Date(
        string='Next Renewal Date',
        required=True,
        tracking=True,
        help='Date this add-on renews (synchronized with the base subscription billing date).',
    )

    # ─── Status ───────────────────────────────────────────────────────────────
    state = fields.Selection([
        ('active', 'Active'),
        ('cancelled', 'Cancelled – Pending Removal'),
        ('expired', 'Expired / Removed'),
    ], string='Status', default='active', required=True, tracking=True)

    billing_cycle = fields.Selection([
        ('monthly', 'Monthly'),
        ('annual', 'Annual'),
    ], string='Billing Cycle', required=True, default='monthly', tracking=True)

    cancel_date = fields.Date(
        string='Cancelled On',
        readonly=True,
        help='Date the customer requested cancellation.',
    )

    # ─── Traceability ─────────────────────────────────────────────────────────
    sale_order_id = fields.Many2one(
        'sale.order',
        string='Sale Order',
        readonly=True,
        index=True,
    )

    order_line_id = fields.Many2one(
        'sale.order.line',
        string='Order Line',
        readonly=True,
    )

    # ─── Display ──────────────────────────────────────────────────────────────
    name = fields.Char(
        string='Description',
        compute='_compute_name',
        store=True,
    )

    # ─── Computed ─────────────────────────────────────────────────────────────
    @api.depends('addon_type', 'quantity', 'monthly_price')
    def _compute_name(self):
        type_labels = dict(self._fields['addon_type'].selection)
        for addon in self:
            label = type_labels.get(addon.addon_type, addon.addon_type or '')
            addon.name = f"{addon.quantity}x {label} @ €{addon.monthly_price:.2f}/unit"

    @api.depends('quantity', 'monthly_price', 'addon_type')
    def _compute_total_monthly(self):
        for addon in self:
            if addon.addon_type == 'storage':
                # Storage price is per-pack, not per-GB
                addon.total_monthly = addon.monthly_price
            else:
                addon.total_monthly = addon.quantity * addon.monthly_price

    # ─── Actions ──────────────────────────────────────────────────────────────
    def action_cancel_addon(self):
        """
        Mark add-on as cancelled.
        It stays active until next_renewal_date; the daily cron _cron_expire_cancelled_addons
        will then remove it from the subscription totals and push updated limits to the tenant.
        """
        for addon in self:
            if addon.state != 'active':
                raise UserError(_('Only active add-ons can be cancelled.'))

            addon.write({
                'state': 'cancelled',
                'cancel_date': fields.Date.today(),
            })

            addon.subscription_id.message_post(
                body=_(
                    "Add-on <b>%(name)s</b> cancelled by customer. "
                    "It will remain active until the next renewal date: <b>%(date)s</b>."
                ) % {
                    'name': addon.name,
                    'date': addon.next_renewal_date,
                }
            )
            _logger.info(
                "Add-on %s (sub: %s) marked cancelled. Effective: %s",
                addon.id, addon.subscription_id.name, addon.next_renewal_date,
            )

    def action_reactivate_addon(self):
        """Reactivate a cancelled add-on (before it has expired)."""
        for addon in self:
            if addon.state != 'cancelled':
                raise UserError(_('Only cancelled add-ons can be reactivated.'))

            addon.write({
                'state': 'active',
                'cancel_date': False,
            })

            addon.subscription_id.message_post(
                body=_("Add-on <b>%s</b> reactivated.") % addon.name
            )

    def action_renew_addon(self):
        """Create a sale order for manual addon renewal"""
        self.ensure_one()
        subscription = self.subscription_id
        
        # 1. Create order
        order = self.env['sale.order'].sudo().create({
            'partner_id': subscription.partner_id.id,
            'saas_company_name': subscription.company_name,
            'saas_plan_id': subscription.plan_id.id,
            'saas_subscription_id': subscription.id,
            'origin': f"Manual Add-on Renewal: {self.name}",
        })

        # 2. Add product line
        product = self.product_id
        if not product:
            # Fallback search logic if product_id is missing from record
            if self.addon_type == 'users':
                code = 'SAAS_EXTRA_USER_ANNUAL' if self.billing_cycle == 'annual' else 'SAAS_EXTRA_USER'
                product = self.env['product.product'].sudo().search([('default_code', '=', code)], limit=1)
            elif self.addon_type == 'storage':
                code = f'SAAS_STORAGE_{self.quantity}GB'
                if self.billing_cycle == 'annual': code += '_ANNUAL'
                product = self.env['product.product'].sudo().search([('default_code', '=', code)], limit=1)

        if product:
             self.env['sale.order.line'].sudo().create({
                'order_id': order.id,
                'product_id': product.id,
                'name': f"{self.billing_cycle.capitalize()} Renewal: {self.name}",
                'product_uom_qty': self.quantity if self.addon_type == 'users' else 1,
                'price_unit': product.list_price,
                'saas_renewed_addon_id': self.id,
                'saas_addon_billing_cycle': self.billing_cycle,
             })
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': order.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.model_create_multi
    def create(self, vals_list):
        addons = super().create(vals_list)
        # Trigger limit push for affected subscriptions
        for sub in addons.mapped('subscription_id'):
            if sub.state == 'active':
                sub.sudo()._push_limits_to_tenant()
        return addons

    def write(self, vals):
        res = super().write(vals)
        # Only trigger if fields that affect quotas change
        if any(f in vals for f in ['state', 'quantity', 'addon_type']):
            for sub in self.mapped('subscription_id'):
                if sub.state == 'active':
                    sub.sudo()._push_limits_to_tenant()
        return res
