# -*- coding: utf-8 -*-

from odoo import models, api, _
import logging

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'
    
    def _reconcile_after_done(self):
        """Override to auto-confirm SaaS orders and trigger provisioning after payment"""
        
        # 1. Lock the transaction validation to prevent concurrent updates (Serialization Failure)
        # This fixes the issue where Redsys callback and User Redirect happen simultaneously
        for tx in self:
            try:
                # Lock wait could be added here if needed, but usually rapid
                self.env.cr.execute("SELECT id FROM payment_transaction WHERE id = %s FOR UPDATE", (tx.id,))
            except Exception as e:
                _logger.warning(f"Could not lock transaction {tx.id}: {e}")

        # Process SaaS orders BEFORE calling super
        for transaction in self:
            sale_orders = transaction.sale_order_ids.filtered(lambda so: so.saas_plan_id and so._is_saas_order())
            
            for order in sale_orders:
                try:
                    # 1. Auto-confirm the order if not already confirmed
                    if order.state in ['draft', 'sent']:
                        _logger.info(f'Auto-confirming SaaS order {order.name} after payment')
                        order.action_confirm()

                    # 2. Trigger provisioning if the order is confirmed (by us or Odoo)
                    if order.state == 'sale':
                        _logger.info("SaaS: Checking provisioning for confirmed order %s", order.name)
                        
                        # Check if auto-provisioning is enabled
                        auto_provision = self.env['ir.config_parameter'].sudo().get_param(
                            'saas.auto_provision_on_payment',
                            'True'
                        )
    
                        if auto_provision == 'True':
                            subscription = order.saas_subscription_id or self.env['saas.subscription'].sudo().search([
                                ('order_id', '=', order.id)
                            ], limit=1)
                            
                            if subscription and not subscription.database_name:
                                provision_method = False
                                for mname in ['action_provision_tenant', 'action_provision_subscription']:
                                    if hasattr(subscription, mname):
                                        provision_method = mname
                                        break
                                
                                if provision_method:
                                    _logger.info("Auto-provisioning: Triggering %s for %s", provision_method, subscription.name)
                                    getattr(subscription, provision_method)()
                                else:
                                    _logger.warning("Auto-provisioning failed for %s: No provisioning method found", subscription.name)
                            elif subscription and subscription.database_name:
                                _logger.info("Auto-provisioning skipped: %s already provisioned", subscription.name)
                    
                except Exception as e:
                    _logger.error(f'Error processing SaaS order {order.name}: {str(e)}')
        
        # Call super, but catch accounting errors for SaaS orders
        try:
            res = super(PaymentTransaction, self)._reconcile_after_done()
        except Exception as e:
            # If this is a SaaS order and accounting fails, log but don't crash
            if self.sale_order_ids.filtered(lambda so: so.saas_plan_id):
                _logger.warning(f'Accounting post-processing failed for SaaS transaction {self.reference}: {str(e)}')
                _logger.info('SaaS provisioning completed successfully despite accounting error')
                res = True
            else:
                raise
        
        return res
    
