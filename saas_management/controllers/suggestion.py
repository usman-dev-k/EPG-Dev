# -*- coding: utf-8 -*-
from odoo import http, fields
from odoo.http import request
import json
import logging
_logger = logging.getLogger(__name__)

class SaasSuggestionController(http.Controller):

    @http.route('/saas/api/suggestion', type='http', auth='none', methods=['POST', 'OPTIONS'], csrf=False, cors='*')
    def submit_suggestion(self, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return request.make_response('', headers=[
                ('Access-Control-Allow-Origin', '*'),
                ('Access-Control-Allow-Methods', 'POST, OPTIONS'),
                ('Access-Control-Allow-Headers', 'Content-Type'),
            ])
            
        import odoo
        from odoo import api
        
        try:
            payload = json.loads(request.httprequest.data)
            database_name = payload.get('database_name')
            email = payload.get('email')
            text = payload.get('text')
            
            # Find main db name (fallback to epg)
            db = request.db or request.session.db or 'crm'
            
            registry = odoo.registry(db)
            with registry.cursor() as cr:
                env = api.Environment(cr, odoo.SUPERUSER_ID, {})
                subscription = env['saas.subscription'].search([('database_name', '=', database_name)], limit=1)
                
                if subscription:
                    env['saas.suggestion'].create({
                        'subscription_id': subscription.id,
                        'email': email,
                        'suggestion_text': text,
                        'state': 'new'
                    })
                    msg = f"<b>New Suggestion from {email}:</b><br/>{text}"
                    subscription.message_post(body=msg)
                    return request.make_response(json.dumps({'status': 'success'}), headers=[('Content-Type', 'application/json')])
                    
                return request.make_response(json.dumps({'status': 'error', 'message': 'Subscription not found'}), headers=[('Content-Type', 'application/json')])
        except Exception as e:
            _logger.error("Suggestion error: %s", str(e))
            return request.make_response(json.dumps({'status': 'error', 'message': str(e)}), headers=[('Content-Type', 'application/json')])
