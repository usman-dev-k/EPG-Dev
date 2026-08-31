# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import threading
import logging

_logger = logging.getLogger(__name__)

class SaasUpgradeWizard(models.TransientModel):
    _name = 'saas.upgrade.wizard'
    _description = 'Upgrade Tenant Modules'

    module_names = fields.Char(string='Modules to Upgrade', required=True, default='saas_client', help="Comma-separated list of technical module names (e.g., saas_client,crm)")

    def action_upgrade(self):
        active_ids = self.env.context.get('active_ids', [])
        subscriptions = self.env['saas.subscription'].browse(active_ids).filtered(lambda s: s.database_name)
        
        db_names = subscriptions.mapped('database_name')
        modules = [m.strip() for m in self.module_names.split(',')]
        
        if not db_names or not modules:
            return {'type': 'ir.actions.act_window_close'}

        # Run upgrade in a background thread to prevent UI blocking
        thread = threading.Thread(target=self._upgrade_thread, args=(db_names, modules))
        thread.start()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Upgrade Started'),
                'message': _('Modules %s are being upgraded on %d tenant databases in the background.') % (self.module_names, len(db_names)),
                'type': 'success',
                'sticky': False,
            }
        }

    def _upgrade_thread(self, db_names, modules):
        import odoo
        for db_name in db_names:
            _logger.info("Starting background upgrade for db %s with modules %s", db_name, modules)
            try:
                # 1. Direct SQL to mark modules for upgrade to avoid registry load crashes
                db = odoo.sql_db.db_connect(db_name)
                with db.cursor() as cr:
                    if len(modules) == 1:
                        cr.execute("UPDATE ir_module_module SET state='to upgrade' WHERE name = %s AND state='installed'", (modules[0],))
                    else:
                        cr.execute("UPDATE ir_module_module SET state='to upgrade' WHERE name IN %s AND state='installed'", (tuple(modules),))
                
                # 2. Trigger the actual upgrade by rebuilding the registry in update mode
                registry = odoo.modules.registry.Registry.new(db_name, update_module=True)
                
                _logger.info("Successfully upgraded modules on %s", db_name)
            except Exception as e:
                _logger.error("Failed to upgrade modules on %s: %s", db_name, str(e))
