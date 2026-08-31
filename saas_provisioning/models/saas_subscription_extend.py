# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class SaaSSubscription(models.Model):
    _inherit = 'saas.subscription'
    
    provisioning_status = fields.Selection([
        ('not_started', 'Not Started'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ], string='Provisioning Status', default='not_started', readonly=True)
    
    provisioning_error = fields.Text(string='Provisioning Error', readonly=True)
    admin_password = fields.Char(string='Admin Password', readonly=True, copy=False,
                                  help='Initial admin password for the tenant database')
    
    def write(self, vals):
        # Call super first
        res = super(SaaSSubscription, self).write(vals)
        
        # Check if we need to push limits to tenant
        # Trigger if plan, extra_users, extra_storage changed, or if state became active
        if any(f in vals for f in ['plan_id', 'extra_users', 'extra_storage_gb', 'state']):
            for sub in self:
                if sub.state == 'active' and sub.database_name:
                    sub._push_limits_to_tenant()
        
        # Status Push
        if 'state' in vals:
            for sub in self:
                if sub.database_name:
                     # Map state to simple status
                     status = 'suspended' if sub.state == 'suspended' else 'active'
                     sub._push_status_to_tenant(status)
        
        return res

    def _push_status_to_tenant(self, status):
        """Push subscription status to tenant (active/suspended)"""
        for sub in self:
            if not sub.database_name:
                continue
            
            try:
                _logger.info(f"Pushing status {status} to tenant {sub.database_name}")
                
                import odoo
                registry = odoo.registry(sub.database_name)
                
                with registry.cursor() as cr:
                    env = api.Environment(cr, odoo.SUPERUSER_ID, {})
                    env['ir.config_parameter'].set_param('saas.subscription_status', status)
                    
            except Exception as e:
                _logger.error(f"Failed to push status to tenant {sub.database_name}: {str(e)}")

    def _push_limits_to_tenant(self):
        """Push usage limits to the tenant database parameters"""
        for sub in self:
            if not sub.database_name:
                continue
                
            try:
                # Force refresh of stored computations to ensure addons created just before this call are included
                sub.invalidate_recordset(['total_users', 'total_storage_gb', 'extra_users', 'extra_storage_gb'])
                
                max_users = sub.total_users
                max_storage_mb = int(sub.total_storage_gb * 1024) # GB to MB
                
                _logger.info(f"Pushing limits to {sub.database_name}: Users={max_users}, Storage={max_storage_mb}MB (Sub ID: {sub.id})")
                
                import odoo
                registry = odoo.registry(sub.database_name)
                
                with registry.cursor() as cr:
                    env = api.Environment(cr, odoo.SUPERUSER_ID, {})
                    
                    # atomic update of parameters
                    env['ir.config_parameter'].set_param('saas.max_users', str(max_users))
                    env['ir.config_parameter'].set_param('saas.max_storage_mb', str(max_storage_mb))
                    
                    # Push connection info for portal management
                    if sub.access_token:
                        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
                        env['ir.config_parameter'].set_param('saas.manager_url', base_url)
                        env['ir.config_parameter'].set_param('saas.subscription_token', sub.access_token)
                        
                    # Push AI Assistant config
                    ai_api_key = self.env['ir.config_parameter'].sudo().get_param('ai_assistant.api_key')
                    if ai_api_key:
                        env['ir.config_parameter'].set_param('ai_assistant.api_key', ai_api_key)
                    ai_endpoint = self.env['ir.config_parameter'].sudo().get_param('ai_assistant.endpoint')
                    if ai_endpoint:
                        env['ir.config_parameter'].set_param('ai_assistant.endpoint', ai_endpoint)
                        
                    # Push AI Credits Limit
                    if getattr(sub, 'ai_credits_limit', False):
                        env['ir.config_parameter'].set_param('ai_assistant.message_limit', str(sub.ai_credits_limit))
                    # Also push initial status if not set? 
                    # Usually active on creation, but let's ensure compliance
                    current_status = 'suspended' if sub.state == 'suspended' else 'active'
                    env['ir.config_parameter'].set_param('saas.subscription_status', current_status)
                    
                    # Push expiration date (trial or active)
                    exp_date = sub.trial_end_date if sub.state == 'trial' else sub.expiration_date
                    if exp_date:
                        env['ir.config_parameter'].set_param('saas.expiration_date', str(exp_date))
                    
            except Exception as e:
                _logger.error(f"Failed to push limits to tenant {sub.database_name}: {str(e)}")

    def action_provision_tenant(self):
        """Trigger tenant provisioning asynchronously"""
        self.ensure_one()
        
        if self.database_name:
            raise UserError(_('Tenant already provisioned. Database: %s') % self.database_name)
        
        if not self.company_name:
            raise UserError(_('Company name is required for provisioning'))
        
        # Mark as in progress immediately
        self.write({
            'provisioning_status': 'in_progress',
            'provisioning_error': False
        })
        
        # We will spawn the thread ONLY AFTER the current transaction commits
        import threading
        import odoo
        from odoo import api
        
        sub_id = self.id
        db_name = self.env.cr.dbname
        
        def provision_task():
            try:
                registry = odoo.registry(db_name)
                with registry.cursor() as cr:
                    env = api.Environment(cr, odoo.SUPERUSER_ID, {})
                    provisioning_service = env['saas.provisioning.service']
                    result = provisioning_service.provision_tenant(sub_id)
                    
                    if result:
                        # Push initial limits
                        subscription = env['saas.subscription'].browse(sub_id)
                        subscription._push_limits_to_tenant()
            except Exception as e:
                _logger.error(f"Async provisioning thread failed: {str(e)}")
                
        def spawn_thread():
            thread = threading.Thread(target=provision_task)
            thread.daemon = True
            thread.start()
            
        # Hook into the postcommit phase so it is guaranteed to exist
        self.env.cr.postcommit.add(spawn_thread)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Provisioning Started'),
                'message': _('Tenant is being provisioned in the background. This may take a few minutes.'),
                'type': 'success',
                'sticky': False,
            }
        }
    
    def _schedule_tenant_deletion(self):
        """Override from saas_management to actually delete tenant"""
        _logger.info(f'Scheduling tenant deletion for {self.name}')
        
        # Call deletion service
        provisioning_service = self.env['saas.provisioning.service']
        try:
            provisioning_service.delete_tenant(
                subscription_id=self.id,
                backup=True
            )
        except Exception as e:
            _logger.error(f'Tenant deletion failed for {self.name}: {str(e)}')
            self.write({
                'state': 'error',
                'error_message': f'Deletion failed: {str(e)}'
            })

    @api.model
    def sync_training_videos(self, videos=None):
        import odoo
        # If videos is not provided, sync all
        if not videos:
            if 'saas.training.video' in self.env:
                videos = self.env['saas.training.video'].search([])
            else:
                return

        subs = self.search([('state', 'in', ['active', 'trial', 'suspended']), ('database_name', '!=', False)])
        for sub in subs:
            try:
                registry = odoo.registry(sub.database_name)
                with registry.cursor() as cr:
                    tenant_env = api.Environment(cr, odoo.SUPERUSER_ID, {})
                    if 'saas.training.video' in tenant_env:
                        for video in videos:
                            existing = tenant_env['saas.training.video'].search([('name', '=', video.name)], limit=1)
                            vals = {
                                'category': video.category,
                                'video_url': video.video_url,
                                'description': video.description,
                                'sequence': video.sequence,
                            }
                            if existing:
                                existing.write(vals)
                            else:
                                vals['name'] = video.name
                                tenant_env['saas.training.video'].create(vals)
            except Exception as e:
                _logger.error(f"Failed to sync training videos to tenant {sub.database_name}: {e}")
