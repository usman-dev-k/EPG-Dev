# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)


class SaaSSubscription(models.Model):
	_name = 'saas.subscription'
	_description = 'SaaS Customer Subscription'
	_order = 'create_date desc'
	_inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin']

	name = fields.Char(string='Subscription Reference', required=True, copy=False, readonly=True, default='New')
	
	# Customer Information
	partner_id = fields.Many2one('res.partner', string='Customer', required=True, tracking=True)
	company_name = fields.Char(string='Company Name', required=True, tracking=True)
	company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
	
	# Plan Information
	plan_id = fields.Many2one('saas.plan', string='Plan', required=True, tracking=True)
	billing_cycle = fields.Selection([
		('monthly', 'Monthly'),
		('annual', 'Annual'),
	], string='Billing Cycle', required=True, default='monthly', tracking=True)
	
	# Pricing
	is_early_adopter = fields.Boolean(
		string='Early Adopter',
		default=False,
		tracking=True,
		index=True,
		help='Protected status - cannot be changed once set'
	)
	currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.company.currency_id)
	price = fields.Float(string='Subscription Price (€)', compute='_compute_price', store=True, digits=(10, 2))
	
	# Tenant Information
	database_name = fields.Char(string='Database Name', readonly=True, copy=False, index=True)
	subdomain = fields.Char(string='Subdomain', readonly=True, copy=False, index=True)
	tenant_url = fields.Char(string='Tenant URL', compute='_compute_tenant_url', store=True)
	
	# Access Token for Portal Management
	access_token = fields.Char(string='Access Token', readonly=True, copy=False, index=True)
	
	# Subscription Status
	state = fields.Selection([
		('pending', 'Pending Provisioning'),
		('trial', 'Trial'),
		('active', 'Active'),
		('suspended', 'Suspended'),
		('grace_period', 'Grace Period'),
		('pending_deletion', 'Pending Deletion'),
		('deleted', 'Deleted'),
		('error', 'Error'),
	], string='Status', default='pending', required=True, tracking=True)
	
	# Trial
	trial_start_date = fields.Datetime(string='Trial Start Date', readonly=True)
	trial_end_date = fields.Datetime(string='Trial End Date', readonly=True)
	
	# Dates
	
	def _compute_access_url(self):
		super(SaaSSubscription, self)._compute_access_url()
		for subscription in self:
			subscription.access_url = '/my/subscription/%s' % (subscription.id)
	activation_date = fields.Datetime(string='Activation Date', readonly=True)
	expiration_date = fields.Datetime(string='Expiration Date', tracking=True)
	next_billing_date = fields.Date(string='Next Billing Date')
	
	# Grace Period
	grace_period_start = fields.Datetime(string='Grace Period Start', readonly=True)
	grace_period_end = fields.Datetime(string='Grace Period End', readonly=True, index=True)
	deletion_scheduled_date = fields.Datetime(string='Deletion Scheduled', readonly=True)
	
	# Order Reference
	order_id = fields.Many2one('sale.order', string='Sale Order', readonly=True)
	
	# Add-ons (legacy integer fields — kept for DB compatibility, computed from addon_ids)
	extra_users = fields.Integer(
		string='Extra Users',
		compute='_compute_extra_from_addons',
		store=True,
		help='Total active extra users across all add-on records.'
	)
	extra_storage_gb = fields.Integer(
		string='Extra Storage (GB)',
		compute='_compute_extra_from_addons',
		store=True,
		help='Total active extra storage across all add-on records.'
	)
	# Add-on child records
	addon_ids = fields.One2many(
		'saas.addon',
		'subscription_id',
		string='Add-ons',
	)
	# Totals
	total_users = fields.Integer(string='Total Users', compute='_compute_totals', store=True)
	total_storage_gb = fields.Integer(string='Total Storage (GB)', compute='_compute_totals', store=True)
	
	# Modules
	accounting_module = fields.Boolean(string='Accounting Module', default=False)
	ai_assistant_module = fields.Boolean(string='Módulo asistente de IA', default=False)
	ai_credits_limit = fields.Integer(string='AI Messages Limit', default=0)
	ai_credits_used = fields.Integer(string='AI Messages Used', default=0, readonly=True)
	
	# Payment Email Status
	payment_email_sent = fields.Boolean(string='Payment Confirmation Sent', default=False, copy=False)
	trial_warning_sent = fields.Boolean(string='Trial Warning Sent', default=False, copy=False)
	
	# Error Handling
	error_message = fields.Text(string='Error Message', readonly=True)
	
	# Promo Code
	promo_code_id = fields.Many2one('saas.promo.code', string='Promo Code Used', readonly=True)
	
	# Auto-Renewal
	auto_renew = fields.Boolean(string='Auto-Renew', default=False, tracking=True)
	is_renewable = fields.Boolean(string='Is Renewable', compute='_compute_is_renewable')

	@api.depends('expiration_date', 'state')
	def _compute_is_renewable(self):
		for sub in self:
			if sub.state not in ['active', 'grace_period']:
				sub.is_renewable = False
				continue
				
			if not sub.expiration_date:
				sub.is_renewable = False
				continue
				
			# Renewable if expiration is today or tomorrow (or already expired in grace period)
			now = fields.Datetime.now()
			limit = now + timedelta(days=2)
			
			if sub.expiration_date < now:
				sub.is_renewable = True
			elif sub.expiration_date <= limit:
				sub.is_renewable = True
			else:
				sub.is_renewable = False

	def action_renew_subscription(self):
		"""Create a renewal quotation for this subscription including all active add-ons."""
		self.ensure_one()

		# Security check
		# if not self.is_renewable and not self.env.user.has_group('saas_management.group_saas_manager'):
		# 	raise UserError(_("This subscription cannot be renewed."))

		# Create Sale Order
		order = self.env['sale.order'].create({
			'partner_id': self.partner_id.id,
			'saas_company_name': self.company_name,
			'saas_plan_id': self.plan_id.id,
			'saas_billing_cycle': self.billing_cycle,
			'saas_subscription_origin_id': self.id,
			'auto_renew': self.auto_renew,
		})

		# ── Base Plan Product ────────────────────────────────────────────────
		product = self.plan_id.product_id
		if not product:
			if self.order_id:
				for line in self.order_id.order_line:
					code = line.product_id.default_code or ''
					if any(code.startswith(p) for p in ['SAAS_USER', 'SAAS_EXTRA', 'SAAS_STORAGE', 'SAAS_ACCOUNT', 'SAAS_REAL', 'PROMO_']):
						continue
					product = line.product_id
					break
			if not product:
				raise UserError(_('Product not found for plan "%s". Please configure the Linked Product on the Plan settings.') % self.plan_id.name)

		self.env['sale.order.line'].create({
			'order_id': order.id,
			'product_id': product.id,
			'name': f"Renewal: {self.plan_id.name} ({self.billing_cycle.capitalize()})",
			'product_uom_qty': 1,
			'price_unit': self.price,  # Preserves early adopter / current pricing
		})

		# ── Active Add-ons — Cycle-Aware filtering ────────
		# Monthly: Add-ons are NOT bundled with the main subscription renewal (independent billing).
		# Annual: Add-on (Annual cycle) ARE bundled with the main subscription renewal.
		if self.billing_cycle == 'monthly':
			active_addons = self.env['saas.addon']
		else:
			active_addons = self.addon_ids.filtered(
				lambda a: a.state == 'active' and a.billing_cycle == self.billing_cycle
			)
		for addon in active_addons:
			cycle = self.billing_cycle
			
			if addon.addon_type == 'users':
				xml_id = 'saas_plans.product_extra_user_annual' if cycle == 'annual' else 'saas_plans.product_extra_user'
				addon_product = self.env.ref(xml_id, raise_if_not_found=False)
				if not addon_product: # Fallback to search by code
					code = 'SAAS_EXTRA_USER_ANNUAL' if cycle == 'annual' else 'SAAS_EXTRA_USER'
					addon_product = self.env['product.product'].sudo().search([('default_code', '=', code)], limit=1)
				
				if addon_product:
					self.env['sale.order.line'].create({
						'order_id': order.id,
						'product_id': addon_product.id,
						'name': f"Renewal: {addon_product.name} (x{addon.quantity})",
						'product_uom_qty': addon.quantity,
						'price_unit': addon_product.list_price, # Use price from the product itself
						'saas_renewed_addon_id': addon.id,
					})
			elif addon.addon_type == 'storage':
				suffix = '_annual' if cycle == 'annual' else ''
				storage_map = [
					(25, f'saas_plans.product_storage_25gb{suffix}'),
					(10, f'saas_plans.product_storage_10gb{suffix}'),
					(5, f'saas_plans.product_storage_5gb{suffix}'),
				]
				remaining = addon.quantity
				for size, xml_id in storage_map:
					count = remaining // size
					if count > 0:
						storage_product = self.env.ref(xml_id, raise_if_not_found=False)
						if not storage_product: # Search by code fallback
							code = f'SAAS_STORAGE_{size}GB'
							if cycle == 'annual': code += '_ANNUAL'
							storage_product = self.env['product.product'].sudo().search([('default_code', '=', code)], limit=1)
							
						if storage_product:
							self.env['sale.order.line'].create({
								'order_id': order.id,
								'product_id': storage_product.id,
								'name': f"Renewal: {storage_product.name}",
								'product_uom_qty': count,
								'price_unit': storage_product.list_price, # Always pull direct from product record
								'saas_renewed_addon_id': addon.id,
							})
							remaining -= count * size

		# ── Module Add-ons ───────────────────────────────────────────────────
		# Accounting (Only charge if NOT early adopter)
		if self.accounting_module and not self.is_early_adopter:
			xml_id = 'saas_plans.product_accounting_monthly' if self.billing_cycle == 'monthly' else 'saas_plans.product_accounting_annual'
			module_product = self.env.ref(xml_id, raise_if_not_found=False)
			if module_product:
				self._create_renewal_line(order, module_product)



		# ────────────────────────────────────────────────────────────────────
		
		order.message_subscribe(partner_ids=[self.partner_id.id])
		order.write({'state': 'sent'})  # Visible in portal
		
		return {
			'type': 'ir.actions.act_window',
			'res_model': 'sale.order',
			'res_id': order.id,
			'view_mode': 'form',
			'target': 'current',
		}
	def action_sync_modules(self):
		"""Install missing modules based on the subscription plan and configuration"""
		self.ensure_one()
		if not self.database_name or self.state not in ('active', 'trial'):
			raise UserError(_('Database is not active.'))
			
		# 1. Get expected modules
		prov_service = self.env['saas.provisioning.service']
		expected_modules = prov_service._get_modules_for_plan(self)
		
		# 2. Install them
		if expected_modules:
			db_service = self.env['saas.database.service']
			try:
				db_service.install_modules(self.database_name, expected_modules)
				self.message_post(body=_("Modules synchronized successfully: %s") % ", ".join(expected_modules))
				return {
					'type': 'ir.actions.client',
					'tag': 'display_notification',
					'params': {
						'title': _('Success'),
						'message': _('Modules have been successfully installed/synchronized on the tenant database.'),
						'type': 'success',
						'sticky': False,
					}
				}
			except Exception as e:
				raise UserError(_("Failed to sync modules: %s") % str(e))

	@api.model
	def _cron_sync_modules(self):
		"""Cron job to automatically sync modules for all active databases"""
		active_subs = self.search([('state', 'in', ('active', 'trial')), ('database_name', '!=', False)])
		if not active_subs:
			return
			
		import odoo
		import logging
		_logger = logging.getLogger('cron_mass_sync')
		
		db_name = self.env.cr.dbname
		try:
			registry = odoo.registry(db_name)
			with registry.cursor() as cr:
				env = api.Environment(cr, odoo.SUPERUSER_ID, {})
				subs = env['saas.subscription'].browse(active_subs.ids)
				for sub in subs:
					try:
						expected_modules = env['saas.provisioning.service']._get_modules_for_plan(sub)
						if expected_modules:
							env['saas.database.service'].install_modules(sub.database_name, expected_modules)
					except Exception as e:
						_logger.error(f"Cron failed to sync {sub.database_name}: {e}")
		except Exception as e:
			_logger.error(f"Cron thread failed: {e}")

	def action_mass_sync_modules(self):
		"""Trigger module sync for multiple subscriptions in the background"""
		active_subs = self.filtered(lambda s: s.database_name and s.state in ('active', 'trial'))
		if not active_subs:
			return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {'message': 'No valid active databases selected.', 'type': 'warning'}}
		
		# Define background thread
		def sync_thread(subscription_ids, db_name):
			import odoo
			from odoo import api
			import logging
			_logger = logging.getLogger('mass_sync')
			try:
				registry = odoo.registry(db_name)
				with registry.cursor() as cr:
					env = api.Environment(cr, odoo.SUPERUSER_ID, {})
					subs = env['saas.subscription'].browse(subscription_ids)
					for sub in subs:
						_logger.info(f"Background syncing modules for {sub.database_name}")
						try:
							expected_modules = env['saas.provisioning.service']._get_modules_for_plan(sub)
							if expected_modules:
								env['saas.database.service'].install_modules(sub.database_name, expected_modules)
								sub.message_post(body=f"Background Sync: Modules synchronized successfully.")
						except Exception as e:
							_logger.error(f"Failed to sync {sub.database_name}: {e}")
			except Exception as e:
				_logger.error(f"Thread failed: {e}")

		import threading
		thread = threading.Thread(target=sync_thread, args=(active_subs.ids, self.env.cr.dbname))
		thread.start()

		return {
			'type': 'ir.actions.client',
			'tag': 'display_notification',
			'params': {
				'title': _('Mass Sync Started'),
				'message': _('Modules are being synchronized for %d databases in the background.') % len(active_subs),
				'type': 'success',
				'sticky': False,
			}
		}

	def _create_renewal_line(self, order, product, qty=1):
		self.env['sale.order.line'].create({
			'order_id': order.id,
			'product_id': product.id,
			'name': f"Renewal: {product.name}",
			'product_uom_qty': qty,
		})
        
	@api.model
	def _cron_auto_renew_subscriptions(self):
		"""
		Cron job to automatically generate renewal orders and charge saved cards
		for subscriptions in grace period or suspended states where auto_renew is enabled.
		"""
		subscriptions = self.search([
			('state', 'in', ['grace_period', 'suspended']),
			('auto_renew', '=', True)
		])
		
		for sub in subscriptions:
			try:
				# Check if customer has a valid saved token for Redsys (or any provider)
				token = self.env['payment.token'].search([
					('partner_id', '=', sub.partner_id.id),
					('active', '=', True)
				], limit=1)
				
				if not token:
					_logger.info(f"Auto-Renew skipped for subscription {sub.id}: No saved payment token found for partner {sub.partner_id.name}.")
					continue
					
				# Generate the renewal quotation
				action = sub.action_renew_subscription()
				order_id = action.get('res_id')
				if not order_id:
					continue
					
				order = self.env['sale.order'].browse(order_id)
				_logger.info(f"Auto-Renew processing Order {order.name} for Subscription {sub.id} using token {token.id}")
				
				# Create a transaction for the order using the saved token
				tx_sudo = self.env['payment.transaction'].sudo().create({
					'provider_id': token.provider_id.id,
					'payment_method_id': token.payment_method_id.id if hasattr(token, 'payment_method_id') else False,
					'reference': self.env['payment.transaction']._compute_reference(token.provider_id.code, prefix=order.name),
					'amount': order.amount_total,
					'currency_id': order.currency_id.id,
					'partner_id': order.partner_id.id,
					'token_id': token.id,
					'operation': 'offline',
					'sale_order_ids': [(6, 0, [order.id])],
				})
				
				# Send the S2S request
				tx_sudo._send_payment_request()
				
				# Handle result immediately
				if tx_sudo.state == 'done':
					# The sale.order's automatic confirmation will trigger subscription reactivation (handled in sale.order action_confirm)
					sub.message_post(body=_("Auto-renewal successful. Charged order %s via saved card.") % order.name)
				else:
					sub.message_post(body=_("Auto-renewal failed. Payment transaction %s resulted in state: %s") % (tx_sudo.reference, tx_sudo.state))
			
			except Exception as e:
				_logger.error(f"Error during auto-renew for subscription {sub.id}: {str(e)}")
				sub.message_post(body=_("Auto-renewal encountered an error: %s") % str(e))
	
	def action_upgrade_subscription(self):
		"""Open wizard to upgrade subscription"""
		# For now, just clear the plan in a new order so they can pick? 
		# Or better: redirect to website plans page?
		# "How he do it?" -> Website flow is best.
		# But for backend, let's create a draft order and let user edit.
		
		self.ensure_one()
		order = self.env['sale.order'].create({
			'partner_id': self.partner_id.id,
			'saas_company_name': self.company_name,
			'saas_subscription_origin_id': self.id,
		})
		
		return {
			'type': 'ir.actions.act_window',
			'res_model': 'sale.order',
			'res_id': order.id,
			'view_mode': 'form',
			'target': 'current',
		}

	@api.model
	def _cron_process_subscription_expiry(self):
		"""Process subscription expiration (Active -> Grace Period -> Suspended)"""
		today = fields.Date.today()
		now = fields.Datetime.now()
		
		# 1. Active -> Grace Period
		expired_active = self.search([
			('state', '=', 'active'),
			('expiration_date', '<', now)
		])
		for sub in expired_active:
			sub.write({
				'state': 'grace_period',
				'grace_period_start': now,
				'grace_period_end': now + timedelta(days=7),  # 7 Days Grace
			})
			sub.message_post(body=_("Subscription expired. Entering 7-day grace period."))
			# TODO: Send email
			
		# 2. Grace Period -> Suspended
		expired_grace = self.search([
			('state', '=', 'grace_period'),
			('grace_period_end', '<', now)
		])
		for sub in expired_grace:
			sub.action_suspend_subscription()
			sub.message_post(body=_("Grace period ended. Subscription suspended."))
			# TODO: Send email

	@api.model
	def _cron_process_trial_warning(self):
		"""Send warning email exactly 1 day before trial expiration"""
		now = fields.Datetime.now()
		warning_threshold = now + timedelta(days=1)
		
		# Find trials that expire in less than 24 hours but haven't expired yet
		trials_to_warn = self.search([
			('state', '=', 'trial'),
			('trial_warning_sent', '=', False),
			('trial_end_date', '<=', warning_threshold),
			('trial_end_date', '>', now)
		])
		
		for sub in trials_to_warn:
			# Send the email template
			template = self.env.ref('saas_management.mail_template_trial_warning_es', raise_if_not_found=False)
			if template:
				template.send_mail(sub.id, force_send=True)
				sub.write({'trial_warning_sent': True})
				sub.message_post(body=_("Sent 1-day trial expiration warning email."), subtype_xmlid='mail.mt_note')
			else:
				_logger.error("Could not find mail_template_trial_warning_es")

	@api.model
	def _cron_process_trial_expiration(self):
		"""Process trial expiration (Trial -> Suspended)"""
		print("Process trial expiration (Trial -> Suspended)Process trial expiration (Trial -> Suspended)")
		now = fields.Datetime.now()
		print(now)
		expired_trials = self.search([
			('state', '=', 'trial'),
			('trial_end_date', '<', now)
		])
		print(expired_trials)
		for sub in expired_trials:
			sub.action_suspend_subscription()
			sub.message_post(body=_("5-Day Free Trial ended. Database suspended until subscription is paid."), subtype_xmlid='mail.mt_note')

	@api.model
	def create(self, vals):
		if vals.get('name', 'New') == 'New':
			vals['name'] = self.env['ir.sequence'].next_by_code('saas.subscription') or 'New'
		
		# Generate access token
		if not vals.get('access_token'):
			import uuid
			vals['access_token'] = str(uuid.uuid4())
			
		# Auto-assign early adopter status if plan allows and slots available
		if vals.get('plan_id') and not vals.get('is_early_adopter'):
			plan = self.env['saas.plan'].browse(vals['plan_id'])
			if plan.is_early_adopter and plan.can_use_early_adopter():
				vals['is_early_adopter'] = True
		
		return super(SaaSSubscription, self).create(vals)
	
	def write(self, vals):
		# Auto-set activation date and expiration date when state becomes active
		if vals.get('state') == 'active':
			if not self.activation_date:
				vals['activation_date'] = fields.Datetime.now()
			
			# Set expiration date based on billing cycle if not already set
			if not self.expiration_date and self.billing_cycle:
				if self.billing_cycle == 'annual':
					vals['expiration_date'] = fields.Datetime.now() + timedelta(days=365)
				else:  # monthly
					vals['expiration_date'] = fields.Datetime.now() + timedelta(days=30)
		
		if vals.get('state') == 'deleted':
			for sub in self:
				sub.action_cleanup_before_deletion()
				sub._cleanup_associated_user()
		
		return super(SaaSSubscription, self).write(vals)

	def unlink(self):
		for sub in self:
			sub.action_cleanup_before_deletion()
			sub._cleanup_associated_user()
		return super(SaaSSubscription, self).unlink()

	def action_cleanup_before_deletion(self):
		"""Disable auto-renew and cancel all add-ons before the sub is gone/deleted"""
		self.write({'auto_renew': False})
		active_addons = self.addon_ids.filtered(lambda a: a.state == 'active')
		if active_addons:
			active_addons.write({
				'state': 'cancelled',
				'cancel_date': fields.Date.today(),
			})

	def _cleanup_associated_user(self):
		"""Physically delete the portal user if they have no other active subscriptions"""
		self.ensure_one()
		# check for other active/grace subscriptions for the SAME partner
		other_subs = self.env['saas.subscription'].search([
			('partner_id', '=', self.partner_id.id),
			('state', 'in', ['active', 'grace_period', 'suspended', 'pending']),
			('id', '!=', self.id)
		])
		
		if not other_subs:
			# Focus on DELETING the user account to free up the login/email
			user = self.env['res.users'].sudo().search([('partner_id', '=', self.partner_id.id)], limit=1)
			if user:
				try:
					user_id = user.id
					user_login = user.login
					user.unlink()
					_logger.info(f"Successfully DELETED user {user_login} (ID: {user_id})")
				except Exception as e:
					_logger.warning(f"Could not unlink user {user.login}, falling back to archiving and renaming login: {e}")
					user.write({
						'login': f"deleted_{user.id}_{user.login}",
						'active': False
					})

	def _onchange_plan_id(self):
		"""Auto-assign early adopter status when plan is selected"""
		if self.plan_id and self.plan_id.is_early_adopter:
			if self.plan_id.can_use_early_adopter():
				self.is_early_adopter = True
			else:
				self.is_early_adopter = False

	
	@api.depends('plan_id', 'billing_cycle', 'is_early_adopter')
	def _compute_price(self):
		for subscription in self:
			if not subscription.plan_id:
				subscription.price = 0.0
				continue
			
			plan = subscription.plan_id
			if subscription.billing_cycle == 'annual':
				subscription.price = plan.price_annual
			else:
				subscription.price = plan.price_monthly
	
	@api.depends('subdomain')
	def _compute_tenant_url(self):
		base_domain = self.env['ir.config_parameter'].sudo().get_param('saas.base_domain', 'abc.com')
		for subscription in self:
			if subscription.subdomain:
				subscription.tenant_url = f'https://{subscription.subdomain}.{base_domain}'
			else:
				subscription.tenant_url = False
	
	@api.depends('addon_ids', 'addon_ids.state', 'addon_ids.addon_type', 'addon_ids.quantity')
	def _compute_extra_from_addons(self):
		"""Aggregate active add-on quantities into the legacy integer fields."""
		for sub in self:
			active_addons = sub.addon_ids.filtered(lambda a: a.state == 'active')
			sub.extra_users = sum(
				a.quantity for a in active_addons if a.addon_type == 'users'
			)
			sub.extra_storage_gb = sum(
				a.quantity for a in active_addons if a.addon_type == 'storage'
			) + sub.extra_users  # 1GB free storage per extra user

	@api.depends('plan_id', 'extra_users', 'extra_storage_gb')
	def _compute_totals(self):
		for subscription in self:
			if subscription.plan_id:
				subscription.total_users = subscription.plan_id.included_users + subscription.extra_users
				subscription.total_storage_gb = subscription.plan_id.included_storage_gb + subscription.extra_storage_gb
			else:
				subscription.total_users = subscription.extra_users
				subscription.total_storage_gb = subscription.extra_storage_gb

	def _compute_addon_proration(self, monthly_price, qty=1):
		"""
		Calculate prorated charge for an add-on purchased mid-billing-cycle.
		Formula: (days_remaining / 30) * monthly_price * qty
		Returns the total prorated amount (not per-unit).
		"""
		self.ensure_one()
		from datetime import date
		today = fields.Date.today()
		cycle_end = self.next_billing_date or (self.expiration_date.date() if self.expiration_date else None)

		if not cycle_end or cycle_end <= today:
			# No cycle info or already expired — charge full month
			return round(monthly_price * qty, 2), 30

		days_remaining = (cycle_end - today).days
		days_in_cycle = 30  # Fixed 30-day billing cycle
		
		# Proration formula: round((days_remaining / 30) * price * qty, 2)
		proration = round((days_remaining / days_in_cycle) * monthly_price * qty, 2)
		
		import logging
		_logger = logging.getLogger(__name__)
		_logger.info(f"Proration Calc: {days_remaining}/{days_in_cycle} days * €{monthly_price} * {qty} qty = €{proration}")
		
		return proration, days_remaining
	
	@api.constrains('is_early_adopter')
	def _check_early_adopter_immutable(self):
		"""Prevent changing early adopter status once set"""
		for subscription in self:
			if subscription.id:
				old_record = self.browse(subscription.id)
				if old_record.is_early_adopter and not subscription.is_early_adopter:
					raise ValidationError(_('Early Adopter status cannot be removed once granted'))
	
	def action_cancel_subscription(self):
		"""User cancels subscription - enters grace period and cancels all active add-ons."""
		for subscription in self:
			if subscription.state not in ['active', 'suspended']:
				raise UserError(_('Only active or suspended subscriptions can be cancelled'))

			# Cancel all active add-ons immediately (subscription is going away)
			active_addons = subscription.addon_ids.filtered(lambda a: a.state == 'active')
			if active_addons:
				active_addons.write({
					'state': 'cancelled',
					'cancel_date': fields.Date.today(),
				})

			subscription.write({
				'state': 'grace_period',
				'grace_period_start': fields.Datetime.now(),
				'grace_period_end': fields.Datetime.now() + timedelta(days=0)
			})

			subscription._send_cancellation_email()
			subscription.message_post(
				body=_('Subscription cancelled. Grace period ends on %s') % subscription.grace_period_end
			)
	
	def action_reactivate_subscription(self):
		"""Reactivate subscription from grace period"""
		for subscription in self:
			if subscription.state != 'grace_period':
				raise UserError(_('Only subscriptions in grace period can be reactivated'))
			
			subscription.write({
				'state': 'active',
				'grace_period_start': False,
				'grace_period_end': False
			})
			
			subscription.message_post(body=_('Subscription reactivated'))
	
	def action_suspend_subscription(self):
		"""Suspend subscription (e.g., payment failed)"""
		for subscription in self:
			subscription.write({'state': 'suspended'})
			subscription.message_post(body=_('Subscription suspended'))
	
	@api.model
	def _cron_process_grace_period_expiration(self):
		"""Cron job to process suspended subscriptions and delete them after 7 days"""
		now = fields.Datetime.now()
		deletion_limit = now - timedelta(days=7)
		
		expired_subscriptions = self.search([
			('state', '=', 'suspended'),
			('grace_period_end', '<=', deletion_limit)
		])
		
		for subscription in expired_subscriptions:
			try:
				subscription.write({
					'state': 'pending_deletion',
					'deletion_scheduled_date': now
				})
				
				# Cleanup all addons for deleted subscription
				subscription.addon_ids.write({'state': 'expired'})
				
				# Schedule deletion (will be handled by provisioning module)
				subscription._schedule_tenant_deletion()
				
				_logger.info(f'Subscription {subscription.name} scheduled for deletion')
				
			except Exception as e:
				_logger.error(f'Failed to schedule deletion for {subscription.name}: {str(e)}')
				subscription.write({
					'state': 'error',
					'error_message': str(e)
				})
	
	@api.model
	def _cron_expire_cancelled_addons(self):
		"""
		Daily cron: expire cancelled OR unpaid overdue add-ons.
		Unpaid addons get a 3-day grace period before being revoked.
		"""
		today = fields.Date.today()
		grace_date = today - timedelta(days=3)
		
		# Domain: (Cancelled AND passed renewal) OR (Active AND overdue by 3+ days)
		domain = ['|', 
			'&', ('state', '=', 'cancelled'), ('next_renewal_date', '<=', today),
			'&', ('state', '=', 'active'), ('next_renewal_date', '<', grace_date)
		]
		expired_addons = self.env['saas.addon'].search(domain)

		if not expired_addons:
			return

		# Group by subscription so we push limits once per subscription
		subscriptions_to_update = self.env['saas.subscription']
		for addon in expired_addons:
			reason = "unpaid overdue" if addon.state == 'active' else "cancelled"
			addon.write({'state': 'expired'})
			subscriptions_to_update |= addon.subscription_id
			_logger.info(
				"Expired %s add-on %s (sub: %s)",
				reason, addon.id, addon.subscription_id.name,
			)
			addon.subscription_id.message_post(
				body=_("Add-on <b>%s</b> has been revoked due to %s status.") % (addon.name, reason)
			)

		# Push updated limits to tenant for each affected subscription
		for sub in subscriptions_to_update:
			try:
				if sub.state == 'active' and sub.database_name:
					sub._push_limits_to_tenant()
				sub.message_post(
					body=_("Cancelled add-on(s) have been removed after billing cycle end.")
				)
			except Exception as e:
				_logger.error(
					"Failed to push limits to tenant %s after addon expiry: %s",
					sub.database_name, str(e),
				)

	def _schedule_tenant_deletion(self):
		"""Schedule tenant deletion - to be implemented by provisioning module"""
		# This will be overridden by saas_provisioning module
		_logger.info(f'Tenant deletion scheduled for {self.name}')
	
	@api.model
	def _cron_auto_renew_addons(self):
		"""
		Independent monthly billing for add-ons (Independent cycle).
		Processes payments using saved tokens and updates renewal dates.
		"""
		today = fields.Date.today()
		
		# 1. Only find active monthly addons for LIVE subscriptions
		due_addons = self.env['saas.addon'].search([
			('state', '=', 'active'),
			('billing_cycle', '=', 'monthly'),
			('next_renewal_date', '<=', today),
			('subscription_id.state', 'in', ['active', 'grace_period', 'suspended']),
			('subscription_id.auto_renew', '=', True),
		])
		
		if not due_addons:
			return
			
		by_sub = {}
		for addon in due_addons:
			sub = addon.subscription_id
			if sub.id not in by_sub:
				by_sub[sub.id] = self.env['saas.addon']
			by_sub[sub.id] |= addon
			
		for sub_id, addons in by_sub.items():
			subscription = self.env['saas.subscription'].browse(sub_id)
			try:
				# 2. Check for payment token
				token = self.env['payment.token'].search([
					('partner_id', '=', subscription.partner_id.id),
					('active', '=', True)
				], limit=1)
				
				if not token:
					_logger.info(f"Add-on Auto-Renew skipped for {subscription.name}: No token.")
					continue

				# 3. Create Sale Order
				order = self.env['sale.order'].sudo().create({
					'partner_id': subscription.partner_id.id,
					'saas_company_name': subscription.company_name,
					'saas_plan_id': subscription.plan_id.id,
					'saas_subscription_id': subscription.id,
					'origin': f"Add-on Renewal: {subscription.name}",
				})
				
				for addon in addons:
					product = False
					billing_cycle = subscription.billing_cycle
					
					if addon.addon_type == 'users':
						user_code = 'SAAS_EXTRA_USER_ANNUAL' if billing_cycle == 'annual' else 'SAAS_EXTRA_USER'
						product = self.env['product.product'].sudo().search([('default_code', '=', user_code)], limit=1)
					elif addon.addon_type == 'storage':
						storage_code = f'SAAS_STORAGE_{addon.quantity}GB'
						if billing_cycle == 'annual':
							storage_code += '_ANNUAL'
						product = self.env['product.product'].sudo().search([
							('default_code', '=', storage_code)
						], limit=1)
						
					if product:
						self.env['sale.order.line'].sudo().create({
							'order_id': order.id,
							'name': f"{billing_cycle.capitalize()} Renewal: {product.name}",
							'product_uom_qty': addon.quantity if addon.addon_type == 'users' else 1,
							'price_unit': product.list_price,
							'saas_renewed_addon_id': addon.id,
							'saas_addon_billing_cycle': billing_cycle,
						})
				
				# 4. Trigger Payment via Redsys Token
				tx_sudo = self.env['payment.transaction'].sudo().create({
					'provider_id': token.provider_id.id,
					'payment_method_id': token.payment_method_id.id if hasattr(token, 'payment_method_id') else False,
					'reference': self.env['payment.transaction']._compute_reference(token.provider_id.code, prefix=order.name),
					'amount': order.amount_total,
					'currency_id': order.currency_id.id,
					'partner_id': order.partner_id.id,
					'token_id': token.id,
					'operation': 'offline',
					'sale_order_ids': [(6, 0, [order.id])],
				})
				
				tx_sudo._send_payment_request()
				
				if tx_sudo.state == 'done':
					# Only confirm if not already handled by payment post-processing
					if order.state in ['draft', 'sent']:
						order.action_confirm() 
					
					invoices = order._create_invoices()
					for inv in invoices:
						inv.action_post()
						# Attempt to reconcile with the transaction payment if any
						tx_sudo._reconcile_after_done()
					_logger.info("Add-on billing successful for %s", subscription.name)
				else:
					_logger.warning("Add-on billing FAILED for %s (TX state: %s)", subscription.name, tx_sudo.state)
					subscription.message_post(body=_("Monthly add-on renewal payment failed. Please check your payment method."))
				
			except Exception as e:
				_logger.error("Cron: Failed to auto-renew addons for sub %s: %s", subscription.name, str(e))

	def _send_cancellation_email(self):
		"""Send email when subscription is cancelled"""
		# TODO: Implement email template
		pass
	
	def action_open_tenant(self):
		"""Open tenant URL in browser"""
		self.ensure_one()
		if not self.tenant_url:
			raise UserError(_('Tenant URL not available'))
		
		return {
			'type': 'ir.actions.act_url',
			'url': self.tenant_url,
			'target': 'new',
		}
	
	def action_open_portal_management(self):
		"""Open management portal for testing/admin usage"""
		self.ensure_one()
		if not self.access_token:
			return
			
		base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
		url = f"{base_url}/saas/manage?token={self.access_token}"
		return {
			'type': 'ir.actions.act_url',
			'url': url,
			'target': 'new',
		}

	def action_provision_subscription(self):
		"""Provision the subscription (Mock implementation for now)"""
		for subscription in self:
			if subscription.state == 'pending':
				# In a real scenario, this would trigger Docker/Kubernetes
				# For now, we just activate it
				
				# Verify subdomain uniqueness or generate one
				if not subscription.subdomain:
					 clean_name = "".join(c for c in subscription.company_name if c.isalnum()).lower()
					 subscription.subdomain = f"{clean_name}-{subscription.id}"
				
				subscription.write({
					'state': 'trial' if order.x_is_free_trial else 'active',
					'activation_date': fields.Datetime.now(),
				})
				subscription.message_post(body=_("Subscription provisioned and activated."), subtype_xmlid='mail.mt_note')
				
				# Send confirmation email
				# subscription._send_provisioning_email()

	@api.model
	def _cron_sync_ai_usage(self):
		"""
		Daily cron: pulls AI message count from tenant databases to update ai_credits_used
		"""
		active_subs = self.search([
			('state', 'in', ['active', 'grace_period']),
			('ai_assistant_module', '=', True),
			('database_name', '!=', False)
		])
		
		for sub in active_subs:
			try:
				import odoo
				registry = odoo.registry(sub.database_name)
				with registry.cursor() as cr:
					env = api.Environment(cr, odoo.SUPERUSER_ID, {})
					count_str = env['ir.config_parameter'].sudo().get_param("ai_assistant.message_count", "0")
					try:
						count = int(count_str)
						sub.ai_credits_used = count
					except ValueError:
						pass
			except Exception as e:
				_logger.error(f"Failed to sync AI usage from tenant {sub.database_name}: {str(e)}")
