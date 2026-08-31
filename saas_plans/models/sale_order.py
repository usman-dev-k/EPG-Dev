# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from datetime import datetime, timedelta
import logging
import psycopg2

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
	_inherit = 'sale.order'
	
	# SaaS-specific fields
	saas_company_name = fields.Char(string='Company Name (for SaaS)')
	saas_plan_id = fields.Many2one('saas.plan', string='SaaS Plan')
	saas_billing_cycle = fields.Selection([
		('monthly', 'Monthly'),
		('annual', 'Annual'),
	], string='Billing Cycle')
	saas_subscription_id = fields.Many2one('saas.subscription', string='Created Subscription', readonly=True)
	saas_subscription_origin_id = fields.Many2one('saas.subscription', string='Subscription to Renew/Upgrade', readonly=True, help='Reference to the subscription being renewed or upgraded')
	
	# Promo code fields
	promo_code_id = fields.Many2one('saas.promo.code', string='Applied Promo Code', readonly=True)
	promo_code_discount = fields.Float(string='Promo Discount', readonly=True, help='Discount amount from promo code')
	
	# Auto-renewal preference
	auto_renew = fields.Boolean(string='Auto-Renew Subscription', default=False, help='Automatically renew subscription when it expires')
	
	def _is_saas_order(self):
		"""Check if the order contains at least one SaaS-related product"""
		self.ensure_one()
		return any(line.product_id.default_code and line.product_id.default_code.startswith('SAAS_') 
				   for line in self.order_line)

	def _cart_update(self, product_id=None, line_id=None, add_qty=0, set_qty=0, **kwargs):
		"""Override to clear SaaS fields if SaaS products are removed from cart"""
		res = super(SaleOrder, self)._cart_update(product_id=product_id, line_id=line_id, add_qty=add_qty, set_qty=set_qty, **kwargs)
		
		# If it was a SaaS order but no longer has SaaS products, clear the metadata
		if self.saas_plan_id and not self._is_saas_order():
			_logger.info(f"Clearing SaaS metadata for order {self.name} as SaaS products were removed from cart")
			self.write({
				'saas_plan_id': False,
				'saas_company_name': False,
				'saas_billing_cycle': False,
				'auto_renew': False,
			})
		return res
	
	
	def action_confirm(self):
		"""Override to create subscription when order is confirmed"""
		res = super(SaleOrder, self).action_confirm()
		
		# Create subscription for SaaS orders
		for order in self:
			if order.saas_plan_id and order.saas_company_name and order._is_saas_order():
				order._create_saas_subscription()
			
			# Automatic Invoicing for SaaS orders
			if order.saas_plan_id and order._is_saas_order():
				try:
					# Create invoice
					invoices = order._create_invoices()
					# Post invoice
					for invoice in invoices:
						invoice.action_post()
				except Exception as e:
					_logger.error(f"Failed to auto-invoice SaaS order {order.name}: {str(e)}")
		
		return res
	
	def _create_saas_subscription(self):
		"""Create or Update SaaS subscription from sale order"""
		self.ensure_one()
		
		try:
			if not self._is_saas_order():
				_logger.warning(f"Attempted to create SaaS subscription for order {self.name} but no SaaS products found.")
				return False

			# Check if this is an update (Renewal/Upgrade) to an existing subscription
			# Use origin_id if set (explicit), otherwise check if we already created one (idempotency)
			subscription = self.saas_subscription_origin_id or self.saas_subscription_id
			is_update = bool(subscription)
			
			# Determine if early adopter status should be granted (Only for new subs)
			is_early_adopter = False
			if not is_update:
				if self.saas_plan_id.is_early_adopter:
					# Double check limit before confirming
					if not self.saas_plan_id.can_use_early_adopter():
						# Fallback can be implemented here
						is_early_adopter = False
					else:
						is_early_adopter = True
				elif self.promo_code_id and self.promo_code_id.grant_early_adopter:
					is_early_adopter = True
			
			# Calculate Add-ons
			extra_users = 0
			extra_storage = 0
			accounting_module = False
			ai_assistant_module = False
			ai_credits = 0
			
			if is_early_adopter or (is_update and subscription.is_early_adopter):
				accounting_module = True
			
			for line in self.order_line:
				product_code = line.product_id.default_code or ''
				
				# Additional Users
				if product_code == 'SAAS_USER' or product_code == 'SAAS_EXTRA_USER':
					extra_users += int(line.product_uom_qty)
				
				# Additional Storage
				elif product_code.startswith('SAAS_STORAGE_'):
					if '5GB' in product_code:
						extra_storage += 5 * int(line.product_uom_qty)
					elif '10GB' in product_code:
						extra_storage += 10 * int(line.product_uom_qty)
					elif '25GB' in product_code:
						extra_storage += 25 * int(line.product_uom_qty)
				
				# Modules
				elif product_code.startswith('SAAS_ACCOUNTING'):
					accounting_module = True
				elif product_code == 'SAAS_AI_ASSISTANT':
					ai_assistant_module = True
					ai_credits += 5000 * int(line.product_uom_qty)

			
			# Bonus storage for additional users (1 GB per user)
			extra_storage += extra_users
			
			if is_update:
				# ── Update existing subscription ──────────────────────────────────────
				vals = {}

				# Module enablement (unchanged)
				if accounting_module and not subscription.accounting_module:
					vals['accounting_module'] = True
				if ai_assistant_module and not subscription.ai_assistant_module:
					vals['ai_assistant_module'] = True
				if ai_credits > 0:
					vals['ai_credits_limit'] = subscription.ai_credits_limit + ai_credits

				
				# Plan Change (Upgrade)
				if self.saas_plan_id and self.saas_plan_id != subscription.plan_id:
					vals['plan_id'] = self.saas_plan_id.id
					vals['billing_cycle'] = self.saas_billing_cycle
					
					# Reset expiration for Upgrade (Start fresh cycle)
					start_date = fields.Datetime.now()
					if self.saas_billing_cycle == 'annual':
						vals['expiration_date'] = start_date + timedelta(days=365)
					else:
						vals['expiration_date'] = start_date + timedelta(days=30)
					
					_logger.info(f'Subscription %s upgraded to %s', subscription.name, self.saas_plan_id.name)
				
				# Renewal (Same Plan)
				elif self.saas_plan_id == subscription.plan_id:
					plan = subscription.plan_id
					plan_product = plan.product_id
					is_full_renewal = False
					has_users_addon = False
					has_storage_addon = False
					
					# Standard product codes for this plan
					expected_codes = [
						f'SAAS_{plan.id}_MONTHLY', 
						f'SAAS_{plan.id}_ANNUAL',
						plan.product_id.default_code if plan.product_id else None
					]
					 
					for line in self.order_line:
						code = line.product_id.default_code or ''
						# Check if this line is the main plan product
						if (plan_product and line.product_id == plan_product) or (code in expected_codes):
							is_full_renewal = True
						elif code.startswith('SAAS_USER') or code.startswith('SAAS_EXTRA_USER'):
							has_users_addon = True
						elif code.startswith('SAAS_STORAGE'):
							has_storage_addon = True
					 
					if is_full_renewal:
						current_expiry = subscription.expiration_date or fields.Datetime.now()
						if current_expiry < fields.Datetime.now():
							current_expiry = fields.Datetime.now()
							
						if self.saas_billing_cycle == 'annual':
							vals['expiration_date'] = current_expiry + timedelta(days=365)
						else:
							vals['expiration_date'] = current_expiry + timedelta(days=30)
							
						_logger.info(f'Subscription %s renewed. New Expiry: %s', subscription.name, vals.get("expiration_date"))
					 
				# Reactivation Safety: 
				# Only move to 'active' if this is a FULL renewal of the plan itself
				# or we are activating a 'pending' or 'trial' subscription.
				# Paying for just a monthly addon should NOT reactivate a suspended/grace annual sub.
				if subscription.state != 'active':
					if is_full_renewal or subscription.state in ['pending', 'trial']:
						vals['state'] = 'active'
						vals['grace_period_start'] = False
						vals['grace_period_end'] = False
					elif subscription.state in ['grace_period', 'suspended']:
						_logger.info("Subscription %s remains in %s state (Partial payment, no plan renewal in order)", subscription.name, subscription.state)

				if self.auto_renew:
					vals['auto_renew'] = True
					
				subscription.write(vals)
				
				new_state = vals.get('state', subscription.state)
				if new_state == 'active' and subscription.database_name:
					subscription._push_limits_to_tenant()
					subscription._push_status_to_tenant('active')
					# Ensure any newly purchased modules (like AI Assistant) are installed
					# We use a post-commit thread to avoid blocking the payment checkout flow for the tenant
					import threading
					import odoo
					from odoo import api
					
					sub_id = subscription.id
					db_name = self.env.cr.dbname
					
					def sync_task():
						try:
							registry = odoo.registry(db_name)
							with registry.cursor() as cr:
								env = api.Environment(cr, odoo.SUPERUSER_ID, {})
								sub_sudo = env['saas.subscription'].browse(sub_id)
								sub_sudo.action_sync_modules()
						except Exception as e:
							import logging
							logging.getLogger(__name__).error(f"Failed to auto-sync modules async for {sub_id}: {str(e)}")
							
					def spawn_sync_thread():
						thread = threading.Thread(target=sync_task)
						thread.daemon = True
						thread.start()
						
					self.env.cr.postcommit.add(spawn_sync_thread)
				
				if not self.saas_subscription_id:
					self.write({'saas_subscription_id': subscription.id})
					
			else:
				# ── Create NEW subscription ──────────────────────────────────────────
				subscription = self.env['saas.subscription'].create({
					'partner_id': self.partner_id.id,
					'company_name': self.saas_company_name,
					'plan_id': self.saas_plan_id.id,
					'billing_cycle': self.saas_billing_cycle or 'monthly',
					'order_id': self.id,
					'state': 'pending',
					'is_early_adopter': is_early_adopter,
					'promo_code_id': self.promo_code_id.id if self.promo_code_id else False,
					'accounting_module': accounting_module,
					'ai_assistant_module': True,
					'ai_credits_limit': ai_credits + 5000,
					'auto_renew': self.auto_renew,
				})
				
				self.saas_subscription_id = subscription.id
				
				if self.promo_code_id:
					self.promo_code_id.use_code(self.partner_id.id, subscription.id)
				
				_logger.info(f'Subscription %s created from order %s', subscription.name, self.name)
			
			# ── COMMON LOGIC: Create or Update saas.addon records ─────────────────
			# This runs for both NEW subscriptions and UPDATES to capture
			# extra users and storage purchased in this order.
			for line in self.order_line:
				product_code = line.product_id.default_code or ''
				addon_type = False
				qty = 0
				per_unit_price = line.product_id.list_price

				if product_code in ('SAAS_USER', 'SAAS_EXTRA_USER', 'SAAS_EXTRA_USER_ANNUAL'):
					addon_type = 'users'
					qty = int(line.product_uom_qty)
				elif product_code.startswith('SAAS_STORAGE_'):
					addon_type = 'storage'
					gb_per_unit = 5 if '5GB' in product_code else (10 if '10GB' in product_code else 25)
					qty = gb_per_unit * int(line.product_uom_qty)

				if addon_type and qty > 0:
					# 1. Handle Renewal (Update existing addon)
					if line.saas_renewed_addon_id:
						addon = line.saas_renewed_addon_id
						if addon.billing_cycle == 'monthly':
							new_renewal = (addon.next_renewal_date or fields.Date.today()) + timedelta(days=30)
						else:
							new_renewal = subscription.expiration_date or (fields.Date.today() + timedelta(days=365))
						addon.write({
							'next_renewal_date': new_renewal,
							'state': 'active',
						})
						_logger.info("Renewed %s addon %s: New renewal date %s", addon.billing_cycle, addon.id, new_renewal)
						continue

					# 2. Handle New Purchase (Idempotency check)
					existing_addon = self.env['saas.addon'].search([
						('sale_order_id', '=', self.id),
						('order_line_id', '=', line.id)
					], limit=1)
					
					if not existing_addon:
						line_cycle = line.saas_addon_billing_cycle or subscription.billing_cycle
						if line_cycle == 'monthly':
							next_renewal = fields.Date.today() + timedelta(days=30)
						else:
							next_renewal = subscription.expiration_date or (fields.Date.today() + timedelta(days=365))
						mon_price = per_unit_price if line_cycle == 'monthly' else (per_unit_price / 12.0)
						ann_price = per_unit_price if line_cycle == 'annual' else (per_unit_price * 12.0)
						self.env['saas.addon'].create({
							'subscription_id': subscription.id,
							'product_id': line.product_id.id,
							'addon_type': addon_type,
							'quantity': qty,
							'monthly_price': mon_price,
							'annual_price': ann_price,
							'purchase_date': fields.Date.today(),
							'next_renewal_date': next_renewal,
							'billing_cycle': line_cycle,
							'sale_order_id': self.id,
							'order_line_id': line.id,
							'state': 'active',
						})
						_logger.info('Created new %s addon: %s for %s (%s, Renew: %s)', addon_type, qty, subscription.name, line_cycle, next_renewal)

			# ── Portal User: create/reactivate ONCE per order, isolated in savepoint ──
			if self.partner_id and self.partner_id.email:
				try:
					with self.env.cr.savepoint():
						user = self.env['res.users'].sudo().with_context(active_test=False).search([
							('login', '=', self.partner_id.email)
						], limit=1)
						if user:
							if not user.active:
								user.write({'active': True})
								_logger.info("Reactivated existing user %s", user.login)
						else:
							user = self.env['res.users'].create({
								'name': self.partner_id.name,
								'login': self.partner_id.email,
								'email': self.partner_id.email,
								'partner_id': self.partner_id.id,
								'groups_id': [(6, 0, [self.env.ref('base.group_portal').id])]
							})
							user.action_reset_password()
							_logger.info("Created portal user %s for partner %s", user.login, self.partner_id.name)
				except psycopg2.OperationalError:
					raise
				except Exception as e:
					_logger.error("Failed to create portal user for %s: %s", self.partner_id.name, str(e))
					# Savepoint was rolled back automatically; main transaction continues

			# ── Auto-provisioning: isolated in savepoint so failure doesn't abort tx ──
			try:
				with self.env.cr.savepoint():
					auto_provision = self.env['ir.config_parameter'].sudo().get_param(
						'saas.auto_provision_on_payment', 'True'
					)
					if auto_provision == 'True' and not subscription.database_name:
						provision_method = next(
							(m for m in ['action_provision_tenant', 'action_provision_subscription']
							 if hasattr(subscription, m)),
							None
						)
						if provision_method:
							_logger.info("SaaS: Auto-provisioning %s for %s via Confirm Transition",
										 subscription.name, provision_method)
							getattr(subscription, provision_method)()
						else:
							_logger.warning("SaaS: No provisioning method found for %s", subscription.name)
			except psycopg2.OperationalError:
				raise
			except Exception as e:
				_logger.error("SaaS: Auto-provisioning failed for %s: %s", subscription.name, str(e))
				# Savepoint was rolled back automatically; main transaction continues

		except psycopg2.OperationalError:
			raise
		except Exception as e:
			_logger.error("Failed to process subscription for order %s: %s", self.name, str(e))
			# Don't raise — allow payment to complete and fix subscription manually.
	
	def apply_promo_code(self, promo_code):
		"""Apply promo code to the sale order.
		
		Promo codes grant Early Adopter status to Official plan customers:
		- Official Monthly €59.90 → Early Adopter Monthly €34.90
		- Official Annual €598 → Early Adopter Annual €358
		- Also includes free Accounting module
		"""
		self.ensure_one()
		
		# Check if promo already applied
		if self.promo_code_id:
			return {'success': False, 'message': _('A promo code is already applied. Remove it first to apply a new one.')}
		
		# Check if this is an early adopter plan (promo codes don't work on already discounted plans)
		if self.saas_plan_id and self.saas_plan_id.is_early_adopter:
			return {'success': False, 'message': _('Promo codes cannot be applied to Early Adopter plans (already at Early Adopter pricing).')}
		
		# Find promo code
		promo = self.env['saas.promo.code'].sudo().search([
			('code', '=', promo_code.upper()),
			('active', '=', True)
		], limit=1)
		
		if not promo:
			return {'success': False, 'message': _('Invalid promo code')}
		
		if not promo.can_use():
			return {'success': False, 'message': _('This promo code has expired or reached its usage limit')}
		
		# Only early_adopter type is supported
		if promo.code_type != 'early_adopter':
			return {'success': False, 'message': _('Invalid promo code type')}
		
		# Calculate discount: difference between Official and Early Adopter pricing
		discount_amount = 0.0
		message = ''
		
		if self.saas_billing_cycle == 'monthly':
			# Official Monthly €59.90 → Early Adopter Monthly €34.90
			official_price = self.saas_plan_id.price_monthly
			early_price = self.saas_plan_id.early_adopter_price  # €34.90
			discount_amount = official_price - early_price
			message = f'Early Adopter pricing applied! €{early_price:.2f}/month (was €{official_price:.2f}/month)'
		elif self.saas_billing_cycle == 'annual':
			# Official Annual €598 → Early Adopter Annual €358
			official_price = self.saas_plan_id.price_annual
			# For annual, early_adopter_price stores monthly equivalent (€29.90)
			# The actual annual discount price is stored in early_adopter plan
			early_annual_price = self.saas_plan_id.early_adopter_price * 12  # Approximate
			# But we use the exact configured price from the Early Adopter Annual plan
			early_plan = self.env['saas.plan'].sudo().search([
				('plan_type', '=', 'crm_early'),
				('billing_cycle', '=', 'annual'),
				('active', '=', True)
			], limit=1)
			if early_plan:
				early_annual_price = early_plan.price_annual  # €358
			discount_amount = official_price - early_annual_price
			message = f'Early Adopter pricing applied! €{early_annual_price:.2f}/year (was €{official_price:.2f}/year)'
		
		if discount_amount <= 0:
			return {'success': False, 'message': _('This plan is already at or below Early Adopter pricing')}
		
		# Get or create discount product
		discount_product = self._get_discount_product()
		
		# Create discount line
		self.env['sale.order.line'].create({
			'order_id': self.id,
			'product_id': discount_product.id,
			'name': f'Promo Code: {promo.code} - Early Adopter Discount',
			'product_uom_qty': 1,
			'price_unit': -discount_amount,
			'tax_id': [(5, 0, 0)],  # Remove all taxes
			'is_promo_line': True,
		})
		
		# Store promo code reference
		self.write({
			'promo_code_id': promo.id,
			'promo_code_discount': discount_amount,
		})
		
		return {
			'success': True,
			'message': message,
			'promo_code': promo.code,
			'promo_type': 'Early Adopter',
			'discount_amount': discount_amount,
			'new_total': self.amount_total
		}
	
	def remove_promo_code(self):
		"""Remove applied promo code from the sale order"""
		self.ensure_one()
		
		if not self.promo_code_id:
			return {'success': False, 'message': _('No promo code applied')}
		
		# Remove promo code discount lines
		promo_lines = self.order_line.filtered(lambda l: l.is_promo_line)
		promo_lines.unlink()
		
		# Clear promo code reference
		self.write({
			'promo_code_id': False,
			'promo_code_discount': 0.0,
		})
		
		return {
			'success': True,
			'message': _('Promo code removed'),
			'new_total': self.amount_total
		}
	
	def _get_discount_product(self):
		"""Get or create the discount product for promo codes"""
		discount_product = self.env['product.product'].sudo().search([
			('default_code', '=', 'PROMO_DISCOUNT')
		], limit=1)
		
		if not discount_product:
			discount_product = self.env['product.product'].sudo().create({
				'name': 'Promo Code Discount',
				'default_code': 'PROMO_DISCOUNT',
				'type': 'service',
				'list_price': 0.0,
				'sale_ok': False,
				'purchase_ok': False,
				'invoice_policy': 'order',
			})
		
		return discount_product


class SaleOrderLine(models.Model):
	_inherit = 'sale.order.line'
	
	is_promo_line = fields.Boolean(string='Is Promo Line', default=False)
	saas_renewed_addon_id = fields.Many2one('saas.addon', string='Renewed SaaS Add-on', help='Link to an existing add-on being renewed by this line')
	saas_addon_billing_cycle = fields.Selection([
		('monthly', 'Monthly'),
		('annual', 'Annual'),
	], string='Add-on Billing Cycle')
