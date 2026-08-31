# -*- coding: utf-8 -*-
import binascii
from collections import OrderedDict
from operator import itemgetter

from odoo import fields, http, _
from odoo.exceptions import AccessError, MissingError
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo.tools import groupby as groupbyelem

class SaasPortal(CustomerPortal):

	def _prepare_home_portal_values(self, counters):
		values = super()._prepare_home_portal_values(counters)
		if 'subscription_count' in counters:
			values['subscription_count'] = request.env['saas.subscription'].search_count([
				('partner_id', '=', request.env.user.partner_id.id)
			])
		return values

	@http.route(['/my/subscriptions', '/my/subscriptions/page/<int:page>'], type='http', auth="user", website=True)
	def portal_my_subscriptions(self, page=1, date_begin=None, date_end=None, sortby=None, **kw):
		values = self._prepare_portal_layout_values()
		SaasSubscription = request.env['saas.subscription']
		domain = [('partner_id', '=', request.env.user.partner_id.id)]

		searchbar_sortings = {
			'date': {'label': _('Newest'), 'order': 'create_date desc'},
			'name': {'label': _('Name'), 'order': 'name'},
			'stage': {'label': _('Status'), 'order': 'state'},
		}
		if not sortby:
			sortby = 'date'
		order = searchbar_sortings[sortby]['order']

		# count for pager
		subscription_count = SaasSubscription.search_count(domain)
		# pager
		pager = portal_pager(
			url="/my/subscriptions",
			url_args={'date_begin': date_begin, 'date_end': date_end, 'sortby': sortby},
			total=subscription_count,
			page=page,
			step=self._items_per_page
		)
		# content according to pager and archive selected
		subscriptions = SaasSubscription.search(domain, order=order, limit=self._items_per_page, offset=pager['offset'])
		request.session['my_subscriptions_history'] = subscriptions.ids[:100]

		values.update({
			'date': date_begin,
			'subscriptions': subscriptions,
			'page_name': 'subscription',
			'pager': pager,
			'default_url': '/my/subscriptions',
			'searchbar_sortings': searchbar_sortings,
			'sortby': sortby,
		})
		return request.render("saas_management.portal_my_subscriptions", values)

	@http.route(['/my/subscription/<int:subscription_id>'], type='http', auth="user", website=True)
	def portal_my_subscription_detail(self, subscription_id, access_token=None, **kw):
		subscription = request.env['saas.subscription'].sudo().browse(subscription_id)

		values = {
			'subscription': subscription,
			'page_name': 'subscription',
		}

		values = self._get_page_view_values(
			subscription,
			access_token,
			values,
			'my_subscriptions_history',
			False,
		)

		return request.render(
			'saas_management.portal_my_subscription',
			values
		)


	@http.route(['/my/subscription/<int:subscription_id>/renew'], type='http', auth="user", website=True)
	def portal_renew_subscription(self, subscription_id, access_token=None, **kw):
		try:
		   subscription_sudo = self._document_check_access('saas.subscription', subscription_id, access_token=access_token)
		except (AccessError, MissingError):
			return request.redirect('/my')

		# if not subscription_sudo.is_renewable:
		# 	# If not renewable, just redirect back with a message (or just back)
		# 	return request.redirect(f'/my/subscription/{subscription_id}')

		action = subscription_sudo.sudo().action_renew_subscription()
		
		if isinstance(action, dict) and action.get('res_model') == 'sale.order':
			 order_id = action.get('res_id')
			 # Set website_id, company_id, team_id so it's recognized as a cart for this website
			 order = request.env['sale.order'].sudo().browse(order_id)
			 vals = {
			     'user_id': False, # Remove SystemBot as salesperson
			     'state': 'draft', # Reset to draft so it acts as a cart
			 }
			 if request.website:
			     vals['website_id'] = request.website.id
			     if request.website.company_id:
			         vals['company_id'] = request.website.company_id.id
			     if request.website.salesteam_id:
			         vals['team_id'] = request.website.salesteam_id.id
			 
			 order.write(vals)
			 
			 # set session for direct checkout
			 request.session['sale_last_order_id'] = order_id
			 request.session['sale_order_id'] = order_id
			 return request.redirect('/shop/payment')
			 
		return request.redirect(f'/my/subscription/{subscription_id}')

	@http.route(['/my/subscription/<int:subscription_id>/toggle_auto_renew'], type='http', auth="user", website=True, methods=['POST'])
	def portal_toggle_auto_renew(self, subscription_id, access_token=None, **kw):
		try:
			subscription_sudo = self._document_check_access('saas.subscription', subscription_id, access_token=access_token)
		except (AccessError, MissingError):
			return request.redirect('/my')

		auto_renew_enabled = 'auto_renew' in kw
		subscription_sudo.write({'auto_renew': auto_renew_enabled})
		status_msg = _("Auto-Renew enabled from portal.") if auto_renew_enabled else _("Auto-Renew disabled from portal.")
		subscription_sudo.message_post(body=status_msg)

		return request.redirect(f'/my/subscription/{subscription_id}')

	@http.route(['/my/subscription/<int:subscription_id>/upgrade'], type='http', auth="user", website=True)
	def portal_upgrade_subscription(self, subscription_id, access_token=None, **kw):
		try:
		   subscription_sudo = self._document_check_access('saas.subscription', subscription_id, access_token=access_token)
		except (AccessError, MissingError):
			return request.redirect('/my')

		# If POST, it's a submission (Wait, the form action is /saas/upgrade which is NOT this route)
		# The template says: <form action="/saas/upgrade" method="post">
		# We need to implement /saas/upgrade
		
		# Used for rendering the upgrade page
		values = {
			'subscription': subscription_sudo,
			'page_name': 'subscription',
		}
		return request.render("saas_management.portal_subscription_upgrade", values)

	@http.route(['/saas/upgrade'], type='http', auth="public", website=True, methods=['POST'])
	def portal_subscription_upgrade_submit(self, **kw):
		subscription_id = kw.get('subscription_id')
		access_token = kw.get('access_token')
		
		try:
		   subscription_sudo = self._document_check_access('saas.subscription', int(subscription_id), access_token=access_token)
		except (AccessError, MissingError, ValueError):
			return request.redirect('/my')
			
		add_users = int(kw.get('add_users', 0))
		add_storage = int(kw.get('add_storage', 0))
		add_accounting = kw.get('add_accounting') == 'on'
		add_ai_assistant = int(kw.get('add_ai_assistant', 0))
		
		if add_users <= 0 and add_storage <= 0 and not add_accounting and add_ai_assistant <= 0:
			return request.redirect(f'/my/subscription/{subscription_id}')

		# Create Upsell Order
		vals = {
			'partner_id': subscription_sudo.partner_id.id,
			'saas_company_name': subscription_sudo.company_name,
			'saas_subscription_origin_id': subscription_sudo.id,
			'saas_plan_id': subscription_sudo.plan_id.id, # Required to trigger subscription update logic
		}
		if request.website:
			vals['website_id'] = request.website.id
			if request.website.company_id:
			    vals['company_id'] = request.website.company_id.id
			if request.website.salesteam_id:
			    vals['team_id'] = request.website.salesteam_id.id
			
		order = request.env['sale.order'].sudo().create(vals)
		
		addon_cycle = kw.get('addon_cycle', 'monthly')
		
		# Add Users Line
		if add_users > 0:
			user_product = request.env.ref('saas_plans.product_extra_user', raise_if_not_found=False) or request.env.ref('saas_plans.product_saas_user', raise_if_not_found=False)
			if user_product:
				if addon_cycle == 'align':
					# Calculate Proration
					price, days = subscription_sudo._compute_addon_proration(user_product.list_price, qty=add_users)
					line_name = f"Upgrade: {add_users} Extra Users (Prorated for {days} days)"
					product_uom_qty = 1
				else:
					# Monthly (Flat full month)
					price = user_product.list_price
					line_name = f"Upgrade: {add_users} Extra Users (Monthly)"
					product_uom_qty = add_users

				request.env['sale.order.line'].sudo().create({
					'order_id': order.id,
					'product_id': user_product.id,
					'name': line_name,
					'product_uom_qty': product_uom_qty,
					'price_unit': price,
					'saas_addon_billing_cycle': addon_cycle if addon_cycle != 'align' else 'annual',
				})
				
		# Add Storage Line
		if add_storage > 0:
			# Map to product based on size
			xml_id = f'saas_plans.product_storage_{add_storage}gb'
			product = request.env.ref(xml_id, raise_if_not_found=False)
			if product:
				if addon_cycle == 'align':
					# Calculate Proration
					price, days = subscription_sudo._compute_addon_proration(product.list_price, qty=1)
					line_name = f"Upgrade: {add_storage} GB Storage (Prorated for {days} days)"
				else:
					# Monthly
					price = product.list_price
					line_name = f"Upgrade: {add_storage} GB Storage (Monthly)"

				request.env['sale.order.line'].sudo().create({
					'order_id': order.id,
					'product_id': product.id,
					'name': line_name,
					'product_uom_qty': 1,
					'price_unit': price,
					'saas_addon_billing_cycle': addon_cycle if addon_cycle != 'align' else 'annual',
				})
		
		# Add Accounting Module Line
		add_accounting = kw.get('add_accounting') == 'on'
		if add_accounting:
			product_xml_id = 'saas_plans.product_accounting_monthly' if subscription_sudo.billing_cycle == 'monthly' else 'saas_plans.product_accounting_annual'
			acc_product = request.env.ref(product_xml_id, raise_if_not_found=False)
			if acc_product:
				if addon_cycle == 'align':
					# Calculate Proration
					price, days = subscription_sudo._compute_addon_proration(acc_product.list_price, qty=1)
					line_name = f"Upgrade: Accounting Module (Prorated for {days} days)"
				else:
					# Monthly
					price = acc_product.list_price
					line_name = "Upgrade: Accounting Module"
					
				request.env['sale.order.line'].sudo().create({
					'order_id': order.id,
					'product_id': acc_product.id,
					'name': line_name,
					'product_uom_qty': 1,
					'price_unit': price,
					'saas_addon_billing_cycle': addon_cycle if addon_cycle != 'align' else 'annual',
				})

		# Add AI Assistant Line (One-off)
		if add_ai_assistant > 0:
			ai_product = request.env.ref('saas_plans.product_ai_assistant', raise_if_not_found=False)
			if ai_product:
				request.env['sale.order.line'].sudo().create({
					'order_id': order.id,
					'product_id': ai_product.id,
					'name': f"AI Assistant ({add_ai_assistant * 5000} Messages)",
					'product_uom_qty': add_ai_assistant,
					'price_unit': ai_product.list_price,
				})
		
		# set session for direct checkout
		request.session['sale_last_order_id'] = order.id
		request.session['sale_order_id'] = order.id
				
		return request.redirect('/shop/payment')

	@http.route(['/saas/addon/cancel'], type='http', auth="public", website=True, methods=['POST'])
	def portal_cancel_addon(self, **kw):
		"""
		Portal route to cancel an individual add-on.
		Authentication via subscription access_token.
		The add-on stays active until next_renewal_date.
		"""
		addon_id = kw.get('addon_id')
		access_token = kw.get('access_token')

		if not addon_id or not access_token:
			return request.redirect('/my')

		try:
			addon_id = int(addon_id)
		except (ValueError, TypeError):
			return request.redirect('/my')

		addon = request.env['saas.addon'].sudo().browse(addon_id)
		if not addon.exists():
			return request.redirect('/my')

		# Verify the access token belongs to the parent subscription
		subscription = addon.subscription_id
		if subscription.access_token != access_token:
			return request.redirect('/my')

		# If logged in, verify the subscription belongs to this user
		public_user = request.env.ref('base.public_user', raise_if_not_found=False)
		if request.env.user != public_user and \
				subscription.partner_id != request.env.user.partner_id:
			return request.redirect('/my')

		try:
			addon.sudo().action_cancel_addon()
		except Exception as e:
			import logging
			logging.getLogger(__name__).error("Addon cancel failed from portal: %s", str(e))

	@http.route(['/my/button/addon/<int:addon_id>/renew'], type='http', auth="user", website=True)
	def portal_renew_addon(self, addon_id, access_token=None, **kw):
		addon = request.env['saas.addon'].sudo().browse(addon_id)
		if not addon.exists():
			return request.redirect('/my')

		# Verify access (Check subscription ownership or token)
		subscription = addon.subscription_id
		try:
			self._document_check_access('saas.subscription', subscription.id, access_token=access_token)
		except (AccessError, MissingError):
			return request.redirect('/my')

		action = addon.sudo().action_renew_addon()
		
		if isinstance(action, dict) and action.get('res_model') == 'sale.order':
			order_id = action.get('res_id')
			order = request.env['sale.order'].sudo().browse(order_id)
			
			# Prepare order for portal checkout
			vals = {'state': 'draft'}
			if request.website:
				vals.update({
					'website_id': request.website.id,
					'company_id': request.website.company_id.id if request.website.company_id else order.company_id.id,
					'team_id': request.website.salesteam_id.id if request.website.salesteam_id else order.team_id.id,
				})
			order.write(vals)

			# Set session for direct checkout
			request.session['sale_last_order_id'] = order_id
			request.session['sale_order_id'] = order_id
			return request.redirect('/shop/payment')

		return request.redirect(f'/my/subscription/{subscription.id}')
