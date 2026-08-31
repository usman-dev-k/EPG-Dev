# -*- coding: utf-8 -*-
from odoo import models, api, _
from odoo.exceptions import ValidationError

class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to check storage limits."""
        # Get limit from system parameters (in MB)
        max_storage_mb = int(self.env['ir.config_parameter'].sudo().get_param('saas.max_storage_mb', '0'))
        
        if max_storage_mb > 0:
            # Calculate total size of new attachments
            new_size = 0
            for vals in vals_list:
                # raw, db_datas, or file_size if available. odoo stores 'file_size' in 15+, 18 definitely has it.
                # But during create, we might only have the data string.
                # However, usually file_size is computed or passed. 
                # Let's look at passed values.
                # If we rely on stored data, we might need to check after checking current usage.
                pass 
                
            # Efficient query for current total usage
            # Sum 'file_size' of all attachments
            self.env.cr.execute("SELECT sum(file_size) FROM ir_attachment")
            result = self.env.cr.fetchone()
            current_usage_bytes = result[0] or 0
            current_usage_mb = current_usage_bytes / (1024 * 1024)
            
            # Let's just check against current usage for now to block "next" upload
            # Or we can check if current + new > max.
            
            # Since calculating new size from base64 string is heavy, we can do a simpler check:
            # If current usage is already > max, block. 
            if current_usage_mb >= max_storage_mb:
                raise ValidationError(_(
                    "You have reached the maximum storage allowed for your subscription plan (%s MB). "
                    "Please upgrade your plan to add more storage."
                ) % max_storage_mb)
                
        return super(IrAttachment, self).create(vals_list)
