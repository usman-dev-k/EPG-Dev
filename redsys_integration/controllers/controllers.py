# -*- coding: utf-8 -*-
# Part of System. See LICENSE file for full copyright and licensing details.

import logging
import sys
from pprint import pprint
import base64

from odoo.fields import Command

from requests.exceptions import ConnectionError, HTTPError
from werkzeug import urls
import requests
from odoo import _, http
from odoo.exceptions import ValidationError, MissingError, AccessError
from odoo.http import request, Response
from odoo.addons.payment.controllers import portal as payment_portal
from odoo.addons.payment.controllers.post_processing import PaymentPostProcessing

import json
_logger = logging.getLogger(__name__)

class RedsysController(http.Controller):

    @http.route(
        '/redsys/payment/transaction/<int:invoice_id>', type='json', auth='public', website=True
    )
    def redsys_payment_transaction(self, invoice_id, access_token, **kwargs):
        try:
            self._document_check_access('account.move', invoice_id, access_token)
        except MissingError as error:
            raise error
        except AccessError:
            raise ValidationError("The access token is invalid.")

        kwargs.pop('custom_create_values', None)
        tx_sudo = self._create_transaction(
            custom_create_values={'invoice_ids': [Command.set([invoice_id])]}, **kwargs,
        )
        
        last_tx_id = request.session.get('__backend_payment_last_tx_id')
        last_tx = request.env['payment.transaction'].browse(last_tx_id).sudo().exists()
        if last_tx:
            PaymentPostProcessing.remove_transactions(last_tx)
        request.session['__backend_payment_last_tx_id'] = tx_sudo.id

        return tx_sudo._get_processing_values()

    @http.route(
        '/payment/redsys/result/redsys_result_ko', type='http', auth='public', website=True, csrf=False, save_session=False
    )
    def redsys_backend_redirec(self, **post):
        return self._redsys_process_response(post)

    def _redsys_process_response(self, data):
        _logger.info("RESPONSE KO")
        _logger.info(str(data))
        parameters = data.get("Ds_MerchantParameters", "")

        parameters_dic = json.loads(base64.b64decode(parameters).decode())
        #reference = urllib.parse.unquote(parameters_dic.get("Ds_MerchantData", ""))
        ref_redsys = int(parameters_dic.get("Ds_Response", "29999"))
        #ref_redsys = data.get('Ds_Response')
        if ref_redsys is None:
            return request.redirect('/shop/payment')
        else:
            request.env['payment.transaction'].sudo()._handle_feedback_data('redsys', data)
            return request.redirect('/payment/status')

    @http.route(
            '/payment/redsys/result/redsys_result_ok', type='http', auth='public', website=True, csrf=False, save_session=False
        )
    def redsys_confirmation_redirec(self, **post):
        _logger.info("RESPONSE OK")
        if post:
            request.env['payment.transaction'].sudo()._handle_feedback_data('redsys', post)
        else:
            _logger.info("Redsys: No params received in OK redirect, skipping feedback processing.")
        return request.redirect('/payment/status')

    @http.route(
            '/payment/redsys/result/redsys_result', type='http', auth='public', website=True, csrf=False, save_session=False
        )
    def redsys_result(self, **post):
        _logger.info("RESPONSE")
        if post:
            request.env['payment.transaction'].sudo()._handle_feedback_data('redsys', post)
        return request.redirect('/payment/status')

