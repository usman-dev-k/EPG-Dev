# -*- coding: utf-8 -*-

from odoo import http, fields, _
from odoo.http import request
import logging
import re
from datetime import timedelta

_logger = logging.getLogger(__name__)

class SaaSPlanController(http.Controller):
	
	@http.route('/saas/plans', type='http', auth='public', website=True)
	def saas_plans(self, **kwargs):
		"""Display available SaaS plans"""
		# Get early adopter plans
		early_plans = request.env['saas.plan'].sudo().search([
			('active', '=', True),
			('plan_type', '=', 'crm_early'),
		], order='sequence')
		
		# Get official plans
		official_plans = request.env['saas.plan'].sudo().search([
			('active', '=', True),
			('plan_type', '=', 'crm_official'),
		], order='sequence')
		
		# Get global early adopter count
		global_ea_count = request.env['saas.plan'].sudo().get_global_early_adopter_count()
		ea_limit = 1000
		ea_remaining = max(0, ea_limit - global_ea_count)
		
		return request.render('saas_plans.saas_plans_page', {
			'early_plans': early_plans,
			'official_plans': official_plans,
			'ea_count': global_ea_count,
			'ea_limit': ea_limit,
			'ea_remaining': ea_remaining,
		})
	
	@http.route('/saas/plan/<int:plan_id>/subscribe', type='http', auth='public', website=True)
	def subscribe_to_plan(self, plan_id, **kwargs):
		"""Subscribe to a SaaS plan"""
		plan = request.env['saas.plan'].sudo().browse(plan_id)
		
		if not plan.exists():
			return request.redirect('/saas/plans')
			
		# Prevent buying if it's an early adopter plan and limit is reached
		if plan.is_early_adopter and not plan.can_use_early_adopter():
			return request.redirect('/saas/plans')
		# Create or get sale order
		order = request.website.sale_get_order(force_create=True)
		
		# Store plan info in session for later use
		request.session['saas_plan_id'] = plan_id
		
		return request.render('saas_plans.subscribe_form', {
			'plan': plan,
			'order': order,
		})
	
	@http.route('/saas/plan/checkout', type='http', auth='public', website=True, methods=['POST'])
	def confirm_subscription(self, **post):
		"""Confirm subscription and add to cart"""
		plan_id = request.session.get('saas_plan_id')
		if not plan_id:
			return request.redirect('/saas/plans')
		
		plan = request.env['saas.plan'].sudo().browse(int(plan_id))
		if not plan.exists():
			return request.redirect('/saas/plans')
			
		if plan.is_early_adopter and not plan.can_use_early_adopter():
			return request.redirect('/saas/plans')
		
		# Get or create sale order
		order = request.website.sale_get_order(force_create=True)
		
		# Get company name and billing cycle from form
		company_name = post.get('company_name', '')
		billing_cycle = post.get('billing_cycle', plan.billing_cycle)
		auto_renew = post.get('auto_renew', '0') == '1'
		
		# Handle partner if public user
		customer_name = post.get('customer_name')
		customer_email = post.get('customer_email')
		
		if customer_name and customer_email and request.env.user._is_public():
			# Check if partner already exists
			partner = request.env['res.partner'].sudo().search([('email', '=', customer_email)], limit=1)
			if not partner:
				partner = request.env['res.partner'].sudo().create({
					'name': customer_name,
					'email': customer_email,
				})
			
			order.sudo().write({
				'partner_id': partner.id,
			})
		
		if not company_name:
			return request.redirect('/saas/plan/%s/subscribe' % plan_id)
		
		# Clear existing subscription from cart if company name changed
		if order.saas_subscription_id and order.saas_subscription_id.company_name != company_name:
			order.sudo().write({'saas_subscription_id': False})

		# Store SaaS-specific data in order
		order.write({
			'saas_plan_id': plan.id,
			'saas_company_name': company_name,
			'saas_billing_cycle': billing_cycle,
			'auto_renew': auto_renew,
		})
		
		# Clear existing SaaS lines to rebuild cart
		order.order_line.filtered(lambda l: l.product_id.default_code and 
								  l.product_id.default_code.startswith('SAAS_')).unlink()
		
		# 1. Add Main Plan Product
		product = self._create_plan_product(plan, billing_cycle)
		order._cart_update(
			product_id=product.id,
			line_id=None,
			add_qty=1,
		)
		
		addon_cycle = post.get('addon_cycle', 'monthly') if billing_cycle == 'annual' else 'monthly'

		# Helper to add product by code
		def add_product_by_code(code, qty=1, price_unit=None, name_override=None, cycle=None):
			prod = request.env['product.product'].sudo().search([('default_code', '=', code)], limit=1)
			if prod:
				res = order._cart_update(
					product_id=prod.id,
					line_id=None,
					add_qty=qty,
				)
				line_id = res.get('line_id')
				if line_id:
					line = request.env['sale.order.line'].sudo().browse(line_id)
					vals = {}
					if price_unit is not None:
						vals['price_unit'] = price_unit
					if name_override:
						vals['name'] = name_override
					if cycle:
						vals['saas_addon_billing_cycle'] = cycle
					if vals:
						line.write(vals)

		# 2. Add Accounting Module
		if post.get('addon_accounting') == '1':
			acc_code = 'SAAS_ACCOUNTING_MONTHLY' if billing_cycle == 'monthly' else 'SAAS_ACCOUNTING_ANNUAL'
			if plan.is_early_adopter:
				# Free for Early Adopters
				add_product_by_code(acc_code, price_unit=0.0, name_override='Accounting Module (Included Free)', cycle=billing_cycle)
			else:
				# Paid for Official
				add_product_by_code(acc_code, cycle=billing_cycle)

		# 3. Add AI Assistant
		ai_qty = int(post.get('ai_assistant_qty', '0'))
		if ai_qty > 0:
			add_product_by_code('SAAS_AI_ASSISTANT', qty=ai_qty)

		# 4. Add Additional Users
		extra_users = int(post.get('extra_users', '0'))
		if extra_users > 0:
			if addon_cycle == 'annual':
				add_product_by_code('SAAS_EXTRA_USER_ANNUAL', qty=extra_users, cycle='annual')
			else:
				add_product_by_code('SAAS_EXTRA_USER', qty=extra_users, cycle='monthly')
			
		# 5. Add Storage Expansion
		storage_gb = int(post.get('storage_expansion', '0'))
		if storage_gb in [5, 10, 25]:
			if addon_cycle == 'annual':
				storage_code = f'SAAS_STORAGE_{storage_gb}GB_ANNUAL'
				add_product_by_code(storage_code, cycle='annual')
			else:
				storage_code = f'SAAS_STORAGE_{storage_gb}GB'
				add_product_by_code(storage_code, cycle='monthly')
		
		checkout_action = post.get('checkout_action')
		if checkout_action == 'trial':
			if not order.saas_subscription_id:
				order.sudo()._create_saas_subscription()
				
			if order.saas_subscription_id and not order.saas_subscription_id.database_name:
				order.saas_subscription_id.sudo().write({
					'state': 'trial',
					'trial_start_date': fields.Datetime.now(),
					'trial_end_date': fields.Datetime.now() + timedelta(days=5),
				})
				try:
					order.saas_subscription_id.sudo().action_provision_tenant()
				except Exception as e:
					_logger.error("Auto-provisioning failed for trial: %s", str(e))
					
			sub_id = order.saas_subscription_id.id if order.saas_subscription_id else ''
			return request.redirect(f'/saas/trial/success?sub_id={sub_id}')
			
		return request.redirect('/shop/checkout')
		
	@http.route('/saas/trial/success', type='http', auth='public', website=True)
	def trial_success(self, sub_id=None, **kwargs):
		"""Show trial success message"""
		sub_id_js = f"'{sub_id}'" if sub_id else "null"
		html_content = f"""
		<!DOCTYPE html>
		<html lang="es">
		<head>
			<meta charset="UTF-8">
			<meta name="viewport" content="width=device-width, initial-scale=1.0">
			<title>Creación en progreso</title>
			<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
			<style>
				:root {{
					--primary: #5A67D8; /* Modern Indigo */
					--bg-color: #0F172A; /* Slate 900 */
					--card-bg: #1E293B; /* Slate 800 */
					--text-main: #F1F5F9; /* Slate 100 */
					--text-muted: #94A3B8; /* Slate 400 */
					--success: #10B981; /* Emerald 500 */
				}}
				body {{
					margin: 0;
					padding: 0;
					font-family: 'Inter', sans-serif;
					background-color: var(--bg-color);
					display: flex;
					align-items: center;
					justify-content: center;
					min-height: 100vh;
					color: var(--text-main);
				}}
				.container {{
					background-color: var(--card-bg);
					padding: 3rem 4rem;
					border-radius: 16px;
					box-shadow: 0 20px 25px -5px rgba(0,0,0,0.5), 0 10px 10px -5px rgba(0,0,0,0.3);
					max-width: 500px;
					text-align: center;
					animation: fadeIn 0.5s ease-out;
					border: 1px solid #334155;
				}}
				.icon-box {{
					width: 80px;
					height: 80px;
					background-color: rgba(16, 185, 129, 0.1);
					border-radius: 50%;
					display: flex;
					align-items: center;
					justify-content: center;
					margin: 0 auto 1.5rem auto;
				}}
				.icon-box svg {{
					width: 40px;
					height: 40px;
					color: var(--success);
				}}
				h1 {{
					font-weight: 800;
					font-size: 1.8rem;
					margin: 0 0 1rem 0;
				}}
				p {{
					font-size: 1rem;
					line-height: 1.6;
					color: var(--text-muted);
					margin: 0 0 2rem 0;
				}}
				.btn {{
					display: inline-block;
					background-color: var(--primary);
					color: white;
					text-decoration: none;
					font-weight: 600;
					padding: 0.8rem 2rem;
					border-radius: 8px;
					transition: all 0.2s ease;
				}}
				.btn:hover {{
					background-color: #434190;
				}}
				@keyframes fadeIn {{
					from {{ opacity: 0; transform: translateY(20px); }}
					to {{ opacity: 1; transform: translateY(0); }}
				}}
				.spinner-border {{
					display: inline-block;
					width: 2rem;
					height: 2rem;
					vertical-align: text-bottom;
					border: .25em solid currentColor;
					border-right-color: transparent;
					border-radius: 50%;
					animation: spinner-border .75s linear infinite;
					margin-bottom: 1rem;
					color: var(--primary);
				}}
				@keyframes spinner-border {{
					100% {{ transform: rotate(360deg); }}
				}}
			</style>
		</head>
		<body>
			<div class="container" id="status_container">
				<div class="spinner-border" id="loading_spinner" role="status"></div>
				<div class="icon-box" id="success_icon" style="display: none;">
					<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
					</svg>
				</div>
				<h1 id="status_title">Creando Base de Datos</h1>
				<p id="status_message">Por favor espere, su base de datos está en creación. Recibirá las credenciales de acceso por correo electrónico en unos minutos.</p>
				<a href="/" class="btn" id="home_btn" style="display: none;" target="_blank">Ir a mi Base de Datos</a>
			</div>
			
			<script>
				document.addEventListener('DOMContentLoaded', function() {{
					const subId = {sub_id_js};
					if (!subId) return;

					const spinner = document.getElementById('loading_spinner');
					const successIcon = document.getElementById('success_icon');
					const title = document.getElementById('status_title');
					const message = document.getElementById('status_message');
					const homeBtn = document.getElementById('home_btn');

					const checkStatus = () => {{
						fetch('/saas/trial/status/' + subId, {{
							method: 'POST',
							headers: {{ 'Content-Type': 'application/json' }},
							body: JSON.stringify({{ jsonrpc: '2.0', method: 'call', params: {{}} }})
						}})
						.then(res => res.json())
						.then(data => {{
							if (data.result && data.result.status === 'completed') {{
								spinner.style.display = 'none';
								successIcon.style.display = 'flex';
								title.innerText = '¡Base de Datos Creada!';
								message.innerText = 'Su entorno está listo. Hemos enviado las credenciales y el enlace de acceso a su correo electrónico.';
								
								if (data.result.url) {{
									homeBtn.href = data.result.url;
								}}
								homeBtn.style.display = 'inline-block';
							}} else if (data.result && data.result.status === 'failed') {{
								spinner.style.display = 'none';
								title.innerText = 'Error en la Creación';
								message.innerText = 'Hubo un problema al crear su base de datos. Por favor, contacte con soporte.';
							}} else {{
								setTimeout(checkStatus, 3000);
							}}
						}})
						.catch(err => {{
							console.error(err);
							setTimeout(checkStatus, 3000);
						}});
					}};
					
					setTimeout(checkStatus, 3000);
				}});
			</script>
		</body>
		</html>
		"""
		return request.make_response(html_content, headers=[('Content-Type', 'text/html')])
		
	@http.route('/saas/trial/status/<int:sub_id>', type='json', auth='public')
	def trial_status(self, sub_id, **kwargs):
		sub = request.env['saas.subscription'].sudo().browse(sub_id)
		if not sub.exists():
			return {'status': 'error'}
		return {
			'status': sub.provisioning_status,
			'url': sub.tenant_url
		}
	
	def _create_plan_product(self, plan, billing_cycle):
		"""Create or get product for a SaaS plan"""
		# First, check if plan has a linked product
		if plan.product_id:
			return plan.product_id
		
		# Fallback: create dynamic product
		product_code = f'SAAS_{plan.id}_{billing_cycle.upper()}'
		
		# Check if product already exists
		product = request.env['product.product'].sudo().search([
			('default_code', '=', product_code)
		], limit=1)
		
		if product:
			return product
		
		# Determine price based on billing cycle
		if billing_cycle == 'monthly':
			price = plan.price_monthly
			name = f'{plan.name} - Monthly'
		else:
			price = plan.price_annual
			name = f'{plan.name} - Annual'
		
		# Create product
		product = request.env['product.product'].sudo().create({
			'name': name,
			'default_code': product_code,
			'type': 'service',
			'list_price': price,
			'sale_ok': True,
			'purchase_ok': False,
			'invoice_policy': 'order',
			'categ_id': request.env.ref('product.product_category_all').id,
			'is_published': True,
		})
		
		return product
	
	@http.route('/saas/apply_promo_code', type='json', auth='public', website=True)
	def apply_promo_code(self, promo_code):
		"""Apply promo code to current sale order"""
		try:
			# Get current sale order from session
			order_id = request.session.get('sale_order_id')
			if not order_id:
				return {'success': False, 'message': _('No active order found')}
			
			order = request.env['sale.order'].sudo().browse(order_id)
			if not order.exists():
				return {'success': False, 'message': _('Order not found')}
			
			# Apply promo code (check is done in the model method)
			result = order.apply_promo_code(promo_code)
			return result
			
		except Exception as e:
			_logger.error(f'Error checking company name: {str(e)}')
			return {'available': False, 'message': _('Error verifying availability.')}

	@http.route('/saas/check_email_availability', type='json', auth='public', website=True)
	def check_email_availability(self, email):
		"""Check if email is already registered as a user"""
		if not email:
			return {'available': True}
		
		user = request.env['res.users'].sudo().search([('login', '=', email)], limit=1)
		if user:
			return {
				'available': False, 
				'message': _('This email is already registered. Please log in to continue.')
			}
		return {'available': True}
	
	@http.route('/saas/remove_promo_code', type='json', auth='public', website=True)
	def remove_promo_code(self):
		"""Remove promo code from current sale order"""
		try:
			# Get current sale order from session
			order_id = request.session.get('sale_order_id')
			if not order_id:
				return {'success': False, 'message': _('No active order found')}
			
			order = request.env['sale.order'].sudo().browse(order_id)
			if not order.exists():
				return {'success': False, 'message': _('Order not found')}
			
			# Remove promo code
			result = order.remove_promo_code()
			return result
			
		except Exception as e:
			_logger.error(f'Error removing promo code: {str(e)}')
			return {'success': False, 'message': _('An error occurred while removing the promo code')}
	
	@http.route('/saas/check_company_name', type='json', auth='public', website=True)
	def check_company_name(self, company_name):
		"""Check if company name/subdomain is available"""
		try:
			# Generate subdomain from company name (Replace spaces with hyphens)
			subdomain = company_name.lower().replace(' ', '-')
			
			# Remove special characters except hyphens
			subdomain = re.sub(r'[^a-z0-9-]', '', subdomain)
			
			# Remove leading/trailing hyphens
			subdomain = subdomain.strip('-')
			
			if not subdomain:
				return {
					'available': False,
					'subdomain': 'invalid',
					'message': 'Please enter a valid company name'
				}
			
			# Check if subdomain already exists in subscriptions (exclude deleted)
			existing = request.env['saas.subscription'].sudo().search([
				('subdomain', '=', subdomain),
				('state', '!=', 'deleted')
			], limit=1)
			
			if existing:
				return {
					'available': False,
					'subdomain': subdomain,
					'message': 'This company name is already taken. Please choose another.'
				}
			
			return {
				'available': True,
				'subdomain': subdomain,
				'message': 'Available!'
			}
			
		except Exception as e:
			_logger.error(f'Error checking company name: {str(e)}')
			return {
				'available': True,  # Allow submission on error
				'subdomain': company_name.lower().replace(' ', ''),
				'message': 'Unable to verify availability'
			}
	@http.route('/my/subscription', type='http', auth='user', website=True)
	def my_subscription(self, **kwargs):
		"""Display user's subscription details (Logged in user)"""
		partner = request.env.user.partner_id
		subscription = request.env['saas.subscription'].sudo().search([
			('partner_id', '=', partner.id),
			('state', 'in', ['active', 'suspended', 'grace_period'])
		], limit=1)
		
		if not subscription:
			return request.render('portal.portal_layout', {
				'page_name': 'subscription',
				'error': 'No active subscription found.'
			})
			
		return request.render('saas_plans.portal_my_subscription', {
			'subscription': subscription,
			'page_name': 'subscription',
		})
	
	@http.route('/saas/manage', type='http', auth='public', website=True)
	def manage_subscription(self, token=None, **kwargs):
		"""Display subscription details via Access Token (No login required)"""
		if not token:
			# Check session
			token = request.session.get('saas_subscription_token')
			
		if not token:
			 return request.redirect('/saas/plans')
			
		subscription = request.env['saas.subscription'].sudo().search([
			('access_token', '=', token)
		], limit=1)
		
		if not subscription:
			return request.render('website.http_error', {
				'status_code': '404',
				'status_message': _('Invalid or expired subscription token.')
			})
		
		# Store token in session for subsequent actions (like upgrade)
		request.session['saas_subscription_token'] = token
		
		return request.render('saas_plans.portal_my_subscription', {
			'subscription': subscription,
			'page_name': 'subscription',
		})

	@http.route('/saas/upgrade', type='http', auth='public', website=True, methods=['POST'])
	def upgrade_subscription(self, **post):
		"""Handle subscription upgrade request"""
		_logger.info("Upgrade Request POST: %s", post)
		
		sub_id = post.get('subscription_id')
		token_from_post = post.get('access_token')
		
		add_users = int(post.get('add_users', 0))
		add_storage = int(post.get('add_storage', 0))
		
		subscription = None
		
		# 1. Try to get subscription by ID if logged in or token is in session
		if sub_id:
			sub = request.env['saas.subscription'].sudo().browse(int(sub_id))
			if sub.exists():
				# if sub.exists():
				# Check ownership: Either logged in user owns it, OR token matches
				
				# Check token from session OR post
				session_token = request.session.get('saas_subscription_token')
				token = token_from_post or session_token
				
				_logger.info("Checking Token. Post: %s, Session: %s, Sub Token: %s", token_from_post, session_token, sub.access_token)
				
				is_owner = False
				if request.env.user._is_public():
					if token and sub.access_token == token:
						is_owner = True
				else:
					# Logged in: Check partner OR token (if admin/testing)
					if sub.partner_id == request.env.user.partner_id:
						is_owner = True
					elif token and sub.access_token == token:
						is_owner = True
						
				if is_owner:
					subscription = sub
		
		if not subscription:
			_logger.warning("Upgrade Failed: Subscription not found or authorized.")
			return request.redirect('/saas/manage')

		# Create upgrade order
		order = request.website.sale_get_order(force_create=True)
		
		_logger.info("Creating Upgrade Order %s for Subscription %s", order.name, subscription.name)
		
		# Link order to subscription
		order.sudo().write({
			'saas_subscription_id': subscription.id,
			'saas_plan_id': subscription.plan_id.id, # Keep same plan
			'saas_company_name': subscription.company_name,
			'partner_id': subscription.partner_id.id, # Link order to correct partner
		})
		
		# Helper to add product
		def add_product(code, qty, price=None):
			product = request.env['product.product'].sudo().search([('default_code', '=', code)], limit=1)
			if product:
				order._cart_update(
					product_id=product.id, 
					add_qty=qty,
					line_id=None
				)
			else:
				_logger.error("Product with code %s not found!", code)

		# Add Users
		if add_users > 0:
			user_code = 'SAAS_EXTRA_USER'
			if subscription.billing_cycle == 'annual':
				user_code = 'SAAS_EXTRA_USER_ANNUAL'
			_logger.info("Upgrading Addon: %s (Qty: %s)", user_code, add_users)
			add_product(user_code, add_users)
			
		# Add Storage
		if add_storage > 0:
			storage_code = f'SAAS_STORAGE_{add_storage}GB'
			if subscription.billing_cycle == 'annual':
				storage_code += '_ANNUAL'
			_logger.info("Upgrading Addon: %s", storage_code)
			add_product(storage_code, 1)
			
		return request.redirect('/shop/checkout')

	@http.route('/saas/check_email_availability', type='json', auth='public', website=True)
	def check_email_availability(self, email):
		"""Check if email is already registered as a user"""
		if not email:
			return {'available': True}
		
		# check for active user with this login
		user = request.env['res.users'].sudo().search([('login', '=', email)], limit=1)
		if user:
			return {
				'available': False, 
				'message': _('This email address is already registered in our system. Please log in to your account first.')
			}
		return {'available': True}
