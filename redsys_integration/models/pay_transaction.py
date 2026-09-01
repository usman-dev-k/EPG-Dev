# Part of System. See LICENSE file for full copyright and licensing details.

import logging
import base64
import hashlib
import hmac
import json
import logging
import urllib
import time
import re
from urllib.parse import urljoin, unquote

from werkzeug import urls
from pprint import pprint

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo import http
from odoo.addons.payment import utils as payment_utils
from odoo.tools import config

_logger = logging.getLogger(__name__)

try:
    from Crypto.Cipher import DES3
except ImportError:
    _logger.info("Dependencia no encontrada (pycryptodome).")

class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    redsys_payment_ref = fields.Char(string="Referencia de pago de Redsys")
    def _get_specific_rendering_values(self, processing_values):
        """ Override of payment to return Redsys-specific rendering values.

        Note: self.ensure_one() from `_get_processing_values`

        :param dict processing_values: The generic and specific processing values of the transaction
        :return: The dict of acquirer-specific processing values
        :rtype: dict
        """
        _logger.info("-- PROCESSING VALUES -- "+str(processing_values))

        res = super()._get_specific_rendering_values(processing_values)

        if self.provider_code != 'redsys' and self.provider_code != 'bizum':

            return res

        base_url = self.provider_id.get_base_url()
        partner_first_name, partner_last_name = payment_utils.split_partner_name(self.partner_name)
        sqlTestMethod = """select state from payment_provider where code = '%s'
                        """ % ('redsys')
        self.env.cr.execute(sqlTestMethod)
        resultTestMethod = self.env.cr.fetchall() or []
        if resultTestMethod:
            (state) = resultTestMethod[0]
        for testMethod in state:
            test = testMethod
        testPayment = 'true' if test == 'test' \
            else 'false'
        lang = 'es' if self.partner_lang == 'es_CO' else 'en'
        reference = self.reference #.split("-")[0]
        
        # sql = """select amount_tax from sale_order where name = '%s'
        #                 """ % (reference)
        # http.request.cr.execute(sql)
        # result = http.request.cr.fetchall() or []
        # if not result:
        #     reference = self.reference
        #     sql = """select amount_tax from sale_order where name = '%s'
        #                 """ % (reference)
        #     http.request.cr.execute(sql)
        #     result = http.request.cr.fetchall() or []
        #     if result:
        #         (amount_tax) = result[0]
        #     else:
        #         reference = processing_values["reference"]

                
        #         _logger.info(str(reference))

        #         sql = """select amount_tax from account_move where name = '%s'
        #                 """ % (reference.split("-")[0])
        #         http.request.cr.execute(sql)
        #         result = http.request.cr.fetchall() or []
        #         _logger.info(str(result))

        #         if result:
        #             (amount_tax) = result[0]
        # else:
        #     (amount_tax) = result[0]     
        _logger.info("-- PROCESSING VALUES -- "+str(processing_values))
           
        # for tax_amount in amount_tax:
        #     tax = tax_amount
        
        # DEBUG: Log the amount being used
        _logger.info(f"DEBUG: Transaction ID={self.id}, self.amount={self.amount}, reference={self.reference}")
        
        values = {
            "Ds_Sermepa_Url": self.provider_id._redsys_get_api_url(),
            "Ds_Merchant_Amount": str(int(round(self.amount * 100))),
            "Ds_Merchant_Currency": self.provider_id.redsys_currency or "978",
            "Ds_Merchant_Order": (
                # str(self.reference) and str(self.reference)[-12:] or False
                str(int(time.time()))
            ),
            "Ds_Merchant_MerchantCode": (
                self.provider_id.redsys_merchant_code and self.provider_id.redsys_merchant_code[:9]
            ),
            "Ds_Merchant_Terminal": self.provider_id.redsys_terminal or "1",
            "Ds_Merchant_TransactionType": (self.provider_id.redsys_transaction_type or "0"),
            "Ds_Merchant_Titular": partner_first_name + ' '+ partner_last_name,
            "Ds_Merchant_MerchantName": (
                self.provider_id.redsys_merchant_name and self.provider_id.redsys_merchant_name[:25]
            ),
            # "Ds_Merchant_MerchantUrl": (
            #     "%s/payment/redsys/return" % (base_url)
            # )[:250],
            'Ds_Merchant_MerchantUrl': urljoin(base_url,'payment/redsys/result/redsys_result'),
            "Ds_Merchant_MerchantData": str(reference),
            # "Ds_Merchant_MerchantData": self.provider_id.redsys_merchant_data or "",
            "Ds_Merchant_ProductDescription": (
                self._product_description(str(self.reference))
                or self.provider_id.redsys_merchant_description
                and self.provider_id.redsys_merchant_description[:125]
            ),
            "Ds_Merchant_ConsumerLanguage": (self.provider_id.redsys_merchant_lang or "001"),
            "Ds_Merchant_UrlOk": urls.url_join(base_url, '/payment/redsys/result/redsys_result_ok'),
            "Ds_Merchant_UrlKo": urls.url_join(base_url, '/payment/redsys/result/redsys_result_ko'),
            "Ds_Merchant_Paymethods": self.provider_id.redsys_pay_method or "T",
        }
        
        # Tokenization support
        if self.tokenize:
            values["Ds_Merchant_Identifier"] = "REQUIRED"
            values["Ds_Merchant_TransactionType"] = "0"
            _logger.info("Redsys: Requesting token generation (Ds_Merchant_Identifier=REQUIRED)")
        elif self.token_id:
            values["Ds_Merchant_Identifier"] = self.token_id.provider_ref
            values["Ds_Merchant_TransactionType"] = "0"
            values["Ds_Merchant_Excep_SCA"] = "MIT"
            _logger.info(f"Redsys: Using existing token: {self.token_id.provider_ref}")
        
        #_logger.info(values)
        
        merchant_parameters = self._url_encode64(json.dumps(values))
        
        return {
                "Ds_SignatureVersion": str(self.provider_id.redsys_signature_version),
                "Ds_MerchantParameters": merchant_parameters.decode("utf-8"),
                "Ds_Signature": self.sign_parameters(
                    self.provider_id.redsys_secret_key, merchant_parameters.decode("utf-8")
                ),
                'api_url': self.provider_id._redsys_get_api_url(),
            }
            
    def _send_payment_request(self):
        """ Override of payment to send a payment request to Redsys.
        
        This is called by Odoo when a transaction is created from a saved token.
        It must execute the S2S (Server-to-Server) REST API call to Redsys.
        """
        super()._send_payment_request()
        if self.provider_code not in ['redsys', 'bizum']:
            return

        if not self.token_id:
            raise ValidationError("Redsys: A token is required for an automatic payment request.")
            
        _logger.info("Redsys: Sending S2S payment request for transaction %s with token %s", self.reference, self.token_id.provider_ref)
        
        import requests
        
        # Prepare the MIT (Merchant Initiated Transaction) parameters
        values = {
            "Ds_Merchant_Amount": str(int(round(self.amount * 100))),
            "Ds_Merchant_Currency": self.provider_id.redsys_currency or "978",
            "Ds_Merchant_Order": str(int(time.time())),
            "Ds_Merchant_MerchantCode": self.provider_id.redsys_merchant_code[:9] if self.provider_id.redsys_merchant_code else "",
            "Ds_Merchant_Terminal": self.provider_id.redsys_terminal or "1",
            "Ds_Merchant_TransactionType": "0",
            "Ds_Merchant_Identifier": self.token_id.provider_ref,
            "Ds_Merchant_DirectPayment": "true", # Bypasses 3DS for Secure-only terminals on S2S
            "Ds_Merchant_Excep_SCA": "MIT", # Exempt from Strong Customer Authentication since we're charging a token automatically
        }
        
        merchant_parameters = self._url_encode64(json.dumps(values)).decode("utf-8")
        signature = self.sign_parameters(self.provider_id.redsys_secret_key, merchant_parameters)
        
        payload = {
            "Ds_SignatureVersion": str(self.provider_id.redsys_signature_version),
            "Ds_MerchantParameters": merchant_parameters,
            "Ds_Signature": signature,
        }
        
        api_url = "https://sis.redsys.es/sis/rest/trataPeticionREST" if self.provider_id.state == 'enabled' else "https://sis-t.redsys.es:25443/sis/rest/trataPeticionREST"
        
        try:
            response = requests.post(api_url, json=payload, timeout=15)
            response.raise_for_status()
            
            response_json = response.json()
            if "Ds_MerchantParameters" not in response_json:
                raise ValidationError(f"Redsys S2S Error: Invalid response format: {response.text}")
                
            resp_params_decoded = json.loads(base64.b64decode(response_json["Ds_MerchantParameters"]).decode("utf-8"))
            response_code = int(resp_params_decoded.get("Ds_Response", "29999"))
            auth_code = resp_params_decoded.get("Ds_AuthorisationCode", "")
            
            state_redsys = self._get_redsys_state(response_code)
            _logger.info("Redsys S2S Response: code=%s state=%s params=%s", response_code, state_redsys, resp_params_decoded)
            
            # Update Odoo transaction based on S2S response
            self.redsys_payment_ref = auth_code
            if state_redsys == 'done':
                self._set_done()
                self._post_process()
            elif state_redsys == 'pending':
                self._set_pending()
            elif state_redsys == 'cancel':
                self._set_canceled()
            else:
                self._set_error(_("Error: %s") % response_code)
                
        except requests.exceptions.RequestException as e:
            _logger.error("Redsys S2S Server Request Failed: %s", str(e))
            self._set_error(_("Redsys server unreachable: %s") % str(e))
        except Exception as e:
            _logger.error("Redsys S2S Processing Error: %s", str(e))
            self._set_error(_("Redsys processing error: %s") % str(e))
            

    @api.model
    def _get_tx_from_feedback_data(self, provider, data):
        _logger.info("TX_FROM_FEEDBACK_DATA")
        _logger.info(data)
        """ Override of payment to find the transaction based on Paypal data.

        :param str provider: The provider of the acquirer that handled the transaction
        :param dict data: The feedback data sent by the provider
        :return: The transaction if found
        :rtype: recordset of `payment.transaction`
        :raise: ValidationError if the data match no transaction
        """
        #tx = super()._get_tx_from_feedback_data(provider, data)

        if provider != 'redsys' and provider != 'bizum':
            return super()._get_tx_from_feedback_data(provider, data)
        try:
            parameters = data.get("Ds_MerchantParameters", "")
            parameters_dic = json.loads(base64.b64decode(parameters).decode())
            reference = unquote(parameters_dic.get("Ds_MerchantData", ""))
            # if len(reference) == 12 and reference[0] == "V":
            #     reference = "IN"+reference
            pay_id = parameters_dic.get("Ds_AuthorisationCode")
            shasign = data.get("Ds_Signature", "").replace("_", "/").replace("-", "+")
            test_env = config["test_enable"]
            _logger.info(parameters_dic)
            _logger.info(reference)
            _logger.info(pay_id)
            _logger.info(test_env)
            _logger.info(shasign)
            if not reference or not pay_id or not shasign:
                error_msg = (
                    "Redsys: received data with missing reference"
                    " (%s) or pay_id (%s) or shashign (%s)" % (reference, pay_id, shasign)
                )
                if not test_env:
                    _logger.info(error_msg)
                    raise ValidationError(error_msg)
            
            tx = self.env['payment.transaction'].search([('reference', '=', reference)])
            
            if tx and tx.payment_id and tx.state == 'done':
                _logger.info(tx.payment_id)
                _logger.info(tx.state)
                return tx
                
            if not tx or len(tx) > 1:
                error_msg = "Redsys: received data for reference %s" % (reference)
                if not tx:
                    error_msg += "; no order found"
                else:
                    error_msg += "; multiple order found"
                if not test_env:
                    _logger.info(error_msg)
                    raise ValidationError(error_msg)
                
            if tx and not test_env:
                shasign_check = self.sign_parameters(
                    tx.provider_id.redsys_secret_key, parameters
                )
                if shasign_check != shasign:
                    error_msg = (
                        "Redsys: invalid shasign, received %s, computed %s, "
                        "for data %s" % (shasign, shasign_check, data)
                    )
                    _logger.info(error_msg)
                    raise ValidationError(error_msg)
                
        except Exception as e:
            raise ValidationError(
                    "Redsys: " + _("No transaction found")
                )
        return tx

    def _process_feedback_data(self, data):
        _logger.info("PROCESS_FEEDBACK_DATA")
        _logger.info(data)
        """ Override of payment to process the transaction based on Redsys data.

        Note: self.ensure_one()

        :param dict data: The feedback data sent by the provider
        :return: None
        :raise: ValidationError if inconsistent data were received
        """
        #super()._process_feedback_data(data)

        if self.provider_code != 'redsys'  and self.provider_code != 'bizum':
            return
        _logger.info(self.payment_id)
        _logger.info(self.state)
        if self.payment_id and self.state == 'done':
            return 
            
        parameters = data.get("Ds_MerchantParameters", "")
        parameters_dic = json.loads(base64.b64decode(parameters).decode())
        reference = unquote(parameters_dic.get("Ds_MerchantData", ""))
        status_code = int(parameters_dic.get("Ds_Response", "29999"))
        state_redsys = self._get_redsys_state(status_code)
        _logger.info("Estado Redsys -> "+str(state_redsys))
        state = state_redsys
        authorisationCode = unquote(parameters_dic.get("Ds_AuthorisationCode"))
        
        # Capture Tokenization details
        if state_redsys == 'done' and self.tokenize:
            token_string = parameters_dic.get("Ds_Merchant_Identifier")
            if token_string and token_string != "REQUIRED":
                # Create the token
                payment_token = self.env['payment.token'].search([
                    ('provider_id', '=', self.provider_id.id),
                    ('provider_ref', '=', token_string)
                ], limit=1)
                
                if not payment_token:
                    # Provide a masked display name like ****1234 if available or a generic descriptor
                    pan = parameters_dic.get('Ds_Card_Number', '')
                    payment_details = pan[-4:] if pan else 'Redsys Token'
                    
                    payment_token = self.env['payment.token'].create({
                        'provider_id': self.provider_id.id,
                        'payment_method_id': self.payment_method_id.id if hasattr(self, 'payment_method_id') and self.payment_method_id else (self.provider_id.payment_method_ids[0].id if self.provider_id.payment_method_ids else False),
                        'partner_id': self.partner_id.id,
                        'provider_ref': token_string,
                        'payment_details': payment_details,
                        'active': True,
                    })
                    _logger.info("Redsys token generated and saved: %s", token_string)
                
                self.token_id = payment_token.id
        
        vals = {
            "state": state,
            "redsys_payment_ref": authorisationCode
        }
        
        tx = ''
        backdata = False
        order_invoice = reference #.split("-")[0]
        if data:
            sql = """select state from sale_order where name = '%s'
                                        """ % (order_invoice)
            self.env.cr.execute(sql)
            result = self.env.cr.fetchall() or []
            if result:
                (state) = result[0]
            else:
                sql = """select state from payment_transaction where reference = '%s'
                                        """ % (reference)
                self.env.cr.execute(sql)
                result = self.env.cr.fetchall() or []
                (state) = result[0]
                backdata = True

            for testMethod in state:
                tx = testMethod
            _logger.info("Result -> "+str(result))

            if tx not in ['draft']:
                if state not in ["done", "pending"]:
                    if backdata:
                        self.manage_status_order(order_invoice, 'payment_transaction')
                    else:
                        self.manage_status_order(order_invoice, 'sale_order')
                else:
                    if state == 1:
                        self.redsys_payment_ref = authorisationCode
                        self._set_done()
                        # _logger.info(f"Line 302{self}")
                        self._post_process()
            else:
                if state_redsys == "done":
                    vals["state_message"] = _("Ok: %s") % parameters_dic.get("Ds_Response")
                    self.redsys_payment_ref = authorisationCode
                    self._set_done()
                    # _logger.info(f"Line 309{self}")
                    self._post_process()
                elif state_redsys == "pending":  # 'Payment error: code: %s.'
                    state_message = _("Error: %s (%s)")
                    self._set_pending()
                elif state_redsys == "cancel":  # 'Payment error: bank unavailable.'
                    state_message = _("Bank Error: %s (%s)")
                    if backdata:
                        self.manage_status_order(order_invoice,'payment_transaction')
                    else:
                        self.manage_status_order(order_invoice,'sale_order')
                    self._set_canceled()
                elif state_redsys == "error":  # 'Payment error: bank unavailable.'
                    # state_message = _("Bank Error: %s (%s)")
                    html_regex = re.compile('<.*?>') 
                    vals["state_message"] = re.sub(html_regex, "", self.provider_id.cancel_msg)
                    _logger.info("Entra error.")
                    if backdata:
                        self.manage_status_order(order_invoice,'payment_transaction')
                    else:
                        self.manage_status_order(order_invoice,'sale_order')
                    self._set_canceled()
                # else:
                #     state_message = _("Redsys: feedback error %s (%s)")
                #     self._set_error(state_message)
            
            self.write(vals)
            return state != "error"

    def _handle_feedback_data(self, provider, data):
        """ Match the transaction with the feedback data, update its state and return it.
        :param str provider: The provider of the acquirer that handled the transaction
        :param dict data: The feedback data sent by the provider
        :return: The transaction
        :rtype: recordset of `payment.transaction`
        """
        tx = self._get_tx_from_feedback_data(provider, data)
        tx._process_feedback_data(data)
        # tx._execute_callback()
        return tx

    def query_update_status(self, table, values, selectors):
        """ Update the table with the given values (dict), and use the columns in
            ``selectors`` to select the rows to update.
        """
        UPDATE_QUERY = "UPDATE {table} SET {assignment} WHERE {condition} RETURNING id"
        setters = set(values) - set(selectors)
        assignment = ",".join("{0}='{1}'".format(s, values[s]) for s in setters)
        condition = " AND ".join("{0}='{1}'".format(s, selectors[s]) for s in selectors)
        query = UPDATE_QUERY.format(
            table=table,
            assignment=assignment,
            condition=condition,
        )
        self.env.cr.execute(query, values)
        self.env.cr.fetchall()

    def reflect_params(self, name, confirmation=False):
        """ Return the values to write to the database. """
        if not confirmation:
            sql = """select state from payment_transaction where reference = '%s'
                                        """ % (name)
            self.env.cr.execute(sql)
            result = self.env.cr.fetchall() or []
            if result:
                return {'reference': name}
                
            else:
                return {'name': name}
        else:
            return {'origin': name}

    def manage_status_order(self, order_name, model_name, confirmation=False):
        condition = self.reflect_params(order_name, confirmation)
        params = {'state': 'draft'}
        self.query_update_status(model_name, params, condition)
        self.query_update_status(model_name, {'state': 'cancel'}, condition)
        

    def _url_encode64(self, data):
        data = base64.b64encode(data.encode())
        return data

    def _url_decode64(self, data):
        return json.loads(base64.b64decode(data).decode("utf-8"))

    def sign_parameters(self, secret_key, params64):
        params_dic = self._url_decode64(params64)
        if "Ds_Merchant_Order" in params_dic:
            order = str(params_dic["Ds_Merchant_Order"])
        else:
            order = str(unquote(params_dic.get("Ds_Order", "Not found")))
        cipher = DES3.new(
            key=base64.b64decode(secret_key), mode=DES3.MODE_CBC, IV=b"\0\0\0\0\0\0\0\0"
        )
        diff_block = len(order) % 8
        zeros = (b"\0" * (8 - diff_block)) if diff_block else b""
        key = cipher.encrypt(str.encode(order + zeros.decode("utf-8")))
        if isinstance(params64, str):
            params64 = params64.encode()
        dig = hmac.new(key=key, msg=params64, digestmod=hashlib.sha256).digest()
        return base64.b64encode(dig).decode("utf-8")
    
    def _product_description(self, order_ref):
        sale_order = self.env["sale.order"].search([("name", "=", order_ref)])
        res = ""
        if sale_order:
            description = "|".join(x.name for x in sale_order.order_line)
            res = description[:125]
        return res        

    
    
    @api.model
    def _get_redsys_state(self, status_code):
        _logger.info("Estado Redsys -> "+str(status_code))
        if 0 <= status_code < 100:
            return "done"
        # elif status_code <= 203:
        #     return "pending"
        elif 912 <= status_code <= 9912:
            return "cancel"
        else:
            return "error"

