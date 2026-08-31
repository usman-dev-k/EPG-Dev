# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError

class ResConfigSettings(models.TransientModel):
	_inherit = 'res.config.settings'

	saas_subscription_token = fields.Char(string='SaaS Token', config_parameter='saas.subscription_token', readonly=True)
	saas_manager_url = fields.Char(string='Manager URL', config_parameter='saas.manager_url', readonly=True)
	saas_client_installed = fields.Boolean(
		compute="_compute_saas_client_installed"
	)

	@api.depends()  # ✅ No dependencies = recomputed fresh every time
	def _compute_saas_client_installed(self):
		installed = bool(self.env['ir.module.module'].sudo().search([
			('name', '=', 'saas_client'),
			('state', '=', 'installed')
		], limit=1))
		for rec in self:
			rec.saas_client_installed = installed
	

	def action_open_subscription_portal(self):
		"""Open the subscription management portal in a new tab"""
		manager_url = self.env['ir.config_parameter'].sudo().get_param('saas.manager_url')
		token = self.env['ir.config_parameter'].sudo().get_param('saas.subscription_token')
		
		if not manager_url or not token:
			raise UserError(_('Subscription connection details not found. Please contact support.'))
		
		url = f"{manager_url}/saas/manage?token={token}"
		
		return {
			'type': 'ir.actions.act_url',
			'url': url,
			'target': 'new',
		}
