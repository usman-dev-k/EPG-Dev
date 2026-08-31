# -*- coding: utf-8 -*-

from odoo import models, api, _
import logging

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def _find_existing_partner(self, email, vat=None):
        """
        Find existing partner by email and optionally VAT/Tax ID.
        
        :param email: Partner email (required)
        :param vat: Partner VAT/Tax ID (optional)
        :return: Existing partner record or empty recordset
        """
        if not email:
            return self.env['res.partner']
        
        domain = [('email', '=ilike', email.strip())]
        
        # If VAT is provided, use it as additional matching criteria
        if vat and vat.strip():
            domain.append(('vat', '=', vat.strip()))
        
        # Search for existing partner
        existing_partner = self.search(domain, limit=1)
        
        if existing_partner:
            _logger.info(f"Found existing partner: {existing_partner.name} (ID: {existing_partner.id}) for email: {email}")
        
        return existing_partner

    @api.model_create_multi
    def create(self, vals_list):
        """
        Override create to check for existing partners before creating new ones.
        This prevents duplicate customer records during checkout.
        """
        deduplicated_vals = []
        existing_partners = self.env['res.partner']
        
        for vals in vals_list:
            email = vals.get('email')
            vat = vals.get('vat')
            
            # Only check for duplicates if email is provided
            if email:
                existing = self._find_existing_partner(email, vat)
                
                if existing:
                    # Partner exists - update instead of create
                    # Only update fields that are not already set or are different
                    update_vals = {}
                    
                    # Update name if provided and different
                    if vals.get('name') and vals.get('name') != existing.name:
                        update_vals['name'] = vals['name']
                    
                    # Update phone if provided and not set
                    if vals.get('phone') and not existing.phone:
                        update_vals['phone'] = vals['phone']
                    
                    # Update address fields if provided and not set
                    if vals.get('street') and not existing.street:
                        update_vals['street'] = vals['street']
                    
                    if vals.get('city') and not existing.city:
                        update_vals['city'] = vals['city']
                    
                    if vals.get('zip') and not existing.zip:
                        update_vals['zip'] = vals['zip']
                    
                    if vals.get('country_id') and not existing.country_id:
                        update_vals['country_id'] = vals['country_id']
                    
                    if vals.get('state_id') and not existing.state_id:
                        update_vals['state_id'] = vals['state_id']
                    
                    # Update VAT if provided and not set
                    if vals.get('vat') and not existing.vat:
                        update_vals['vat'] = vals['vat']
                    
                    # Apply updates if any
                    if update_vals:
                        existing.write(update_vals)
                        _logger.info(f"Updated existing partner {existing.id} with: {update_vals}")
                    
                    # Add to existing partners list instead of creating
                    existing_partners |= existing
                else:
                    # No existing partner found - proceed with creation
                    deduplicated_vals.append(vals)
            else:
                # No email provided - proceed with creation
                deduplicated_vals.append(vals)
        
        # Create only new partners
        new_partners = super(ResPartner, self).create(deduplicated_vals) if deduplicated_vals else self.env['res.partner']
        
        # Return combination of existing and new partners
        return existing_partners | new_partners
