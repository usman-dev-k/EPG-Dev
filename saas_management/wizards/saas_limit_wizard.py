# -*- coding: utf-8 -*-

from odoo import models, fields, api, _

class SaasLimitWizard(models.TransientModel):
    _name = 'saas.limit.wizard'
    _description = 'SaaS Limit Management Wizard'
    
    plan_id = fields.Many2one('saas.plan', string='Plan', required=True)
    current_limit = fields.Integer(string='Current Limit', readonly=True)
    new_limit = fields.Integer(string='New Limit', required=True)
    
    @api.model
    def default_get(self, fields):
        res = super(SaasLimitWizard, self).default_get(fields)
        active_id = self.env.context.get('active_id')
        if active_id:
            plan = self.env['saas.plan'].browse(active_id)
            res.update({
                'plan_id': plan.id,
                'current_limit': plan.early_adopter_limit,
                'new_limit': plan.early_adopter_limit,
            })
        return res
    
    def action_update_limit(self):
        self.ensure_one()
        if self.plan_id:
            # We update the limit. Since limits are global for early adopters, 
            # we might want to update all early adopter plans or just this one 
            # if the logic was per-plan. 
            # Based on requirements, it's a global 1000 limit.
            # But the field is on saas.plan. Let's update it on the specific plan 
            # and potentially others if they share the same backend logic.
            # For this implementation, we simply write to the selected plan.
            self.plan_id.write({'early_adopter_limit': self.new_limit})
            
            # If we want to sync this limit across all early adopter plans:
            if self.plan_id.is_early_adopter:
                other_early_plans = self.env['saas.plan'].search([
                    ('is_early_adopter', '=', True),
                    ('id', '!=', self.plan_id.id)
                ])
                other_early_plans.write({'early_adopter_limit': self.new_limit})
                
        return {'type': 'ir.actions.act_window_close'}
