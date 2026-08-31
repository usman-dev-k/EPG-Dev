# -*- coding: utf-8 -*-

from odoo import http, _
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


class SaaSPaymentController(http.Controller):
    
    @http.route('/saas/payment/success', type='http', auth='user', website=True)
    def payment_success(self, **kwargs):
        """Handle successful payment and trigger provisioning"""
        
        order_id = kwargs.get('order_id')
        
        if not order_id:
            return request.redirect('/saas/plans')
        
        sale_order = request.env['sale.order'].sudo().browse(int(order_id))
        
        if not sale_order.exists():
            return request.redirect('/saas/plans')
        
        return request.render('saas_plans.payment_success', {
            'order': sale_order,
        })
    
    @http.route('/saas/payment/webhook', type='json', auth='public', csrf=False, methods=['POST'])
    def payment_webhook(self, **kwargs):
        """
        Webhook endpoint for payment gateway (Redsys)
        This will be called by Redsys after payment completion
        """
        _logger.info('Payment webhook received: %s', kwargs)
        
        # TODO: Validate webhook signature
        # TODO: Parse Redsys response
        # TODO: Find corresponding sale order
        # TODO: Trigger provisioning
        
        return {'status': 'ok'}
