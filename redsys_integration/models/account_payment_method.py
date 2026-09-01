# -*- coding: utf-8 -*-
# Part of System. See LICENSE file for full copyright and licensing details.

from odoo import api, models


class AccountPaymentMethod(models.Model):
    _inherit = 'account.payment.method'

    @api.model
    def _get_payment_method_information(self):
        res = super()._get_payment_method_information()
        res['redsys'] = {'mode': 'unique', 'domain': [('type', '=', 'bank')]}
        res['bizum'] = {'mode': 'unique', 'domain': [('type', '=', 'bank')]}
        return res
