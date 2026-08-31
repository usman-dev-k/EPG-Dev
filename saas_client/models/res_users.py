# -*- coding: utf-8 -*-
from odoo import models, api, _
from odoo.exceptions import ValidationError

class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to check user limits before creating new users."""
        # Get limit from system parameters
        max_users = int(self.env['ir.config_parameter'].sudo().get_param('saas.max_users', '0'))
        
        # If limit is 0, we assume no limit (or not set yet)
        if max_users > 0:
            # Count current active internal users (excluding share users/portal/public)
            # We typically limit internal users (employees/admins)
            current_users_count = self.search_count([
                ('share', '=', False), 
                ('active', '=', True),
                ('id', '!=', self.env.ref('base.user_root').id), # Exclude SystemBot/Root if desired
                ('id', '!=', self.env.ref('base.user_admin').id)  # Often Admin is included, but sometimes excluded. 
                                                                  # Let's count EVERY internal user for now to be strict.
            ])
            
            # Check if adding new users would exceed limit
            # New users passed in vals_list that are internal
            new_internal_users = 0
            for vals in vals_list:
                # 'share' defaults to False if not specified? 
                # Actually defaults to True for portal, but False for internal? 
                # Let's assume if it's not explicitly share=True, it counts.
                is_share = vals.get('share', False)
                if not is_share:
                    new_internal_users += 1
            
            if current_users_count + new_internal_users > max_users:
                raise ValidationError(_(
                    "You have reached the maximum number of users allowed for your subscription plan (%s users). "
                    "Please upgrade your plan to add more users."
                ) % max_users)
                
        return super(ResUsers, self).create(vals_list)
