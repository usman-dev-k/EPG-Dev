# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class TenantDeletionWizard(models.TransientModel):
    _name = 'saas.tenant.deletion.wizard'
    _description = 'Tenant Deletion Wizard'
    
    subscription_id = fields.Many2one('saas.subscription', string='Subscription', required=True)
    company_name = fields.Char(related='subscription_id.company_name', readonly=True)
    database_name = fields.Char(related='subscription_id.database_name', readonly=True)
    subdomain = fields.Char(related='subscription_id.subdomain', readonly=True)
    
    create_backup = fields.Boolean(string='Create Backup Before Deletion', default=True)
    confirm_deletion = fields.Boolean(string='I confirm this deletion', default=False)
    deletion_reason = fields.Text(string='Reason for Deletion')
    
    @api.model
    def default_get(self, fields_list):
        """Set default subscription from context"""
        res = super(TenantDeletionWizard, self).default_get(fields_list)
        
        # Get active_id from context (the subscription record)
        if self.env.context.get('active_id'):
            res['subscription_id'] = self.env.context.get('active_id')
        
        return res
    
    def action_delete_tenant(self):
        """Execute tenant deletion"""
        self.ensure_one()
        
        if not self.confirm_deletion:
            raise UserError(_('Please confirm the deletion by checking the confirmation box'))
        
        try:
            # Call provisioning service to delete tenant
            provisioning_service = self.env['saas.provisioning.service']
            provisioning_service.delete_tenant(
                subscription_id=self.subscription_id.id,
                backup=self.create_backup
            )
            
            # Log deletion reason
            if self.deletion_reason:
                self.subscription_id.message_post(
                    body=_('Manual deletion. Reason: %s') % self.deletion_reason
                )
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('Tenant deleted successfully'),
                    'type': 'success',
                    'sticky': False,
                }
            }
            
        except Exception as e:
            raise UserError(_('Deletion failed: %s') % str(e))
