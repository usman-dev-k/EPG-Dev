# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request

class SaasClientController(http.Controller):

    @http.route('/suspended', type='http', auth='public', website=False)
    def render_suspended_page(self, **kw):
        """Render a custom HTML page when the subscription is suspended."""
        manager_url = request.env['ir.config_parameter'].sudo().get_param('saas.manager_url', '')
        
        # HTML Template for the suspended page
        html_content = f"""
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Base de Datos Suspendida</title>
            <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
            <style>
                :root {{
                    --primary: #5A67D8; /* Modern Indigo */
                    --primary-hover: #434190;
                    --bg-color: #0F172A; /* Slate 900 */
                    --card-bg: #1E293B; /* Slate 800 */
                    --text-main: #F1F5F9; /* Slate 100 */
                    --text-muted: #94A3B8; /* Slate 400 */
                    --danger: #EF4444; /* Red 500 */
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
                    background-color: rgba(239, 68, 68, 0.1);
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin: 0 auto 1.5rem auto;
                }}
                .icon-box svg {{
                    width: 40px;
                    height: 40px;
                    color: var(--danger);
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
                    box-shadow: 0 4px 6px rgba(90, 103, 216, 0.25);
                }}
                .btn:hover {{
                    background-color: var(--primary-hover);
                    transform: translateY(-2px);
                    box-shadow: 0 6px 12px rgba(90, 103, 216, 0.3);
                }}
                @keyframes fadeIn {{
                    from {{ opacity: 0; transform: translateY(20px); }}
                    to {{ opacity: 1; transform: translateY(0); }}
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="icon-box">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                </div>
                <h1>Base de Datos Suspendida</h1>
                <p>El período de prueba de 7 días ha finalizado o su suscripción ha sido suspendida. Para restaurar el acceso completo a su base de datos, por favor proceda con el pago iniciando sesión en el portal de gestión.</p>
                {"<a href='https://epgcrm.com/web/login' class='btn'>Renovar Suscripción</a>" }
            </div>
        </body>
        </html>
        """
        
        return request.make_response(html_content, headers=[('Content-Type', 'text/html')])

    @http.route('/saas_client/submit_suggestion', type='json', auth='user')
    def submit_suggestion(self, suggestion):
        import requests
        
        manager_db = request.env['ir.config_parameter'].sudo().get_param('saas.manager_db', 'crm')
        db_name = request.env.cr.dbname
        user_email = request.env.user.email or request.env.user.login
        
        try:
            import odoo
            from odoo import api
            
            # Connect directly to the manager database (since both DBs are on the same Odoo instance)
            registry = odoo.registry(manager_db)
            with registry.cursor() as cr:
                env = api.Environment(cr, odoo.SUPERUSER_ID, {})
                subscription = env['saas.subscription'].search([('database_name', '=', db_name)], limit=1)
                
                if subscription:
                    env['saas.suggestion'].create({
                        'subscription_id': subscription.id,
                        'email': user_email,
                        'suggestion_text': suggestion,
                        'state': 'new'
                    })
                    msg = f"<b>New Suggestion from {user_email}:</b><br/>{suggestion}"
                    subscription.message_post(body=msg)
                    return {'status': 'success'}
                else:
                    return {'status': 'error', 'message': f'Subscription for {db_name} not found in manager database'}
        except Exception as e:
            return {'status': 'error', 'message': f'Database connection error: {str(e)}'}
from odoo.addons.web.controllers.home import Home
import base64

class SaasHome(Home):
    @http.route()
    def web_client(self, s_action=None, **kw):
        if request.session.uid:
            # We use sudo to avoid access rights issues if they are restricted
            user = request.env['res.users'].sudo().browse(request.session.uid)
            manager_db = request.env['ir.config_parameter'].sudo().get_param('saas.manager_db', 'crm')
            if request.env.cr.dbname != manager_db:
                if user._is_admin() and not user.company_id.saas_onboarding_done:
                    return request.redirect('/saas/onboarding')
        return super(SaasHome, self).web_client(s_action, **kw)


class SaasOnboardingController(http.Controller):
    
    @http.route('/saas/onboarding', type='http', auth='user', website=True)
    def saas_onboarding(self, **kw):
        user = request.env.user
        if not user._is_admin() or user.company_id.sudo().saas_onboarding_done:
            return request.redirect('/web')
            
        countries = request.env['res.country'].sudo().search([])
        return request.render('saas_client.saas_onboarding_template', {
            'company': user.company_id.sudo(),
            'countries': countries,
        })

    @http.route('/saas/onboarding/process', type='http', auth='user', methods=['POST'], csrf=True)
    def saas_onboarding_process(self, **post):
        import json
        import base64
        import logging
        _logger = logging.getLogger(__name__)
        
        user = request.env.user
        if not user._is_admin() or user.company_id.sudo().saas_onboarding_done:
            return request.redirect('/web')
            
        company = user.company_id.sudo()
        env = request.env
        
        try:
            payload_str = post.get('payload_json', '{}')
            data = json.loads(payload_str)
            
            # --- 1. Company & Tax Data (Steps 1 & 2) ---
            company_vals = {
                'saas_client_type': data.get('client_type'),
                'name': data.get('legal_name', company.name),
                'saas_commercial_name': data.get('commercial_name'),
                'vat': data.get('vat'),
                'street': data.get('street'),
                'zip': data.get('zip'),
                'city': data.get('city'),
                'phone': data.get('phone'),
                'website': data.get('website'),
                'saas_activity_type': data.get('activity_type'),
                'saas_main_objective': data.get('main_objective'),
                'saas_user_count_expected': data.get('user_count'),
                'saas_use_quotations': data.get('use_quotations'),
                'saas_use_sales_followup': data.get('use_sales_followup'),
                'saas_issue_invoices': data.get('issue_invoices'),
                'saas_record_supplier_invoices': data.get('record_supplier_invoices'),
                'saas_use_accounting': data.get('use_accounting'),
                'saas_accounting_handler': data.get('accounting_handler'),
                'email': data.get('main_email'),
                'saas_wants_ai': data.get('wants_ai'),
                'saas_import_strategy': data.get('import_strategy'),
                'saas_onboarding_done': True
            }

            if data.get('state_name'):
                state = env['res.country.state'].sudo().search([('name', 'ilike', data.get('state_name')), ('country_id', '=', int(data.get('country_id')))], limit=1)
                if state:
                    company_vals['state_id'] = state.id

            if data.get('country_id'):
                company_vals['country_id'] = int(data.get('country_id'))
                
            logo_file = request.httprequest.files.get('company_logo')
            if logo_file and logo_file.filename:
                company_vals['logo'] = base64.b64encode(logo_file.read())
                
            company.write(company_vals)
            
            # --- 2. Users & Permissions (Step 5) ---
            invited_users = data.get('invited_users', [])
            for u in invited_users:
                if u.get('email') and u.get('name'):
                    # Check if user exists
                    existing = env['res.users'].sudo().search([('login', '=', u['email'])], limit=1)
                    if not existing:
                        # Determine groups based on role
                        group_ids = [env.ref('base.group_user').id] # Basic Internal User
                        if u['role'] == 'manager':
                            sales_mgr = env.ref('sales_team.group_sale_manager', raise_if_not_found=False)
                            if sales_mgr: group_ids.append(sales_mgr.id)
                        elif u['role'] == 'admin':
                            sys_admin = env.ref('base.group_system', raise_if_not_found=False)
                            if sys_admin: group_ids.append(sys_admin.id)
                            
                        new_user = env['res.users'].sudo().create({
                            'name': u['name'],
                            'login': u['email'],
                            'email': u['email'],
                            'company_id': company.id,
                            'company_ids': [(4, company.id)],
                            'groups_id': [(6, 0, group_ids)]
                        })
                        # Send invitation email (Odoo standard reset password / invite)
                        new_user.action_reset_password()
            
            # --- 3. Sales & Pipeline Setup (Step 6) ---
            if data.get('use_quotations') or data.get('use_sales_followup'):
                sales_team = env.ref('sales_team.team_sales_department', raise_if_not_found=False)
                if not sales_team:
                    sales_team = env['crm.team'].sudo().search([('company_id', 'in', [company.id, False])], limit=1)
                if sales_team:
                    sales_team.sudo().write({'use_quotations': data.get('use_quotations'), 'use_opportunities': data.get('use_sales_followup')})
            
            # --- 4. Accounting Setup (Step 7) ---
            if data.get('issue_invoices') or data.get('record_supplier_invoices') or data.get('use_accounting'):
                # In Odoo 16+, load the Spanish Chart of Accounts (España - Completo 2008) directly using the code 'es_full'
                try:
                    if company.chart_template != 'es_full':
                        env['account.chart.template'].sudo().try_loading('es_full', company=company, install_demo=False)
                        _logger.info(f"Successfully loaded es_full chart of accounts for {company.name}")
                except Exception as e:
                    _logger.error(f"Failed to load chart of accounts: {str(e)}")

        except Exception as e:
            _logger.error(f"Error processing onboarding: {str(e)}")
            # Even if something fails, we mark it done so they don't get stuck forever, 
            # but in a real prod system we might want to show an error page.
            company.write({'saas_onboarding_done': True})
            
        return request.redirect('/web')
