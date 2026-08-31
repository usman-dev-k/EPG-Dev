# -*- coding: utf-8 -*-

from odoo import models, api, _
from odoo.exceptions import UserError
import subprocess
import os
import logging

_logger = logging.getLogger(__name__)


class SaaSDatabaseService(models.AbstractModel):
    _name = 'saas.database.service'
    _description = 'SaaS Database Management Service'
    
    def _db_exists_direct(self, db_name):
        """
        Check if a database exists by querying PostgreSQL directly.
        This avoids odoo.service.db.exp_db_exist() which is blocked when list_db=False.
        """
        try:
            import odoo.sql_db
            with odoo.sql_db.db_connect('postgres').cursor() as cr:
                cr.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
                return bool(cr.fetchone())
        except Exception as e:
            _logger.warning(f'Could not check db existence via postgres db, trying direct: {e}')
            try:
                import psycopg2
                conn = psycopg2.connect(database=db_name)
                conn.close()
                return True
            except Exception:
                return False

    @api.model
    def create_database(self, db_name, admin_password='admin', template_db='template_basic'):
        """
        Create a new SaaS tenant database by cloning a template database.
        """
        try:
            _logger.info(f'Creating database: {db_name}')

            # Check existence without using the blocked exp_db_exist
            if self._db_exists_direct(db_name):
                raise UserError(_('Database %s already exists') % db_name)

            import odoo
            from odoo.service.db import exp_duplicate_database

            # Step 1: Clone the template database
            template_db = self.env['ir.config_parameter'].sudo().get_param('saas.template_db', template_db)
            
            _logger.info(f'Duplicating template {template_db} to {db_name}')
            
            # Temporarily bypass list_db=False restriction for the cloning process
            original_list_db = odoo.tools.config.get('list_db')
            odoo.tools.config['list_db'] = True
            try:
                exp_duplicate_database(template_db, db_name)
            finally:
                odoo.tools.config['list_db'] = original_list_db

            _logger.info(f'Template duplicated successfully to {db_name}. Updating password...')

            # Step 2: set admin password on the cloned database
            registry = odoo.registry(db_name)
            with registry.cursor() as cr:
                env = api.Environment(cr, odoo.SUPERUSER_ID, {})
                admin_user = env['res.users'].search([('login', '=', 'admin')], limit=1)
                if not admin_user:
                    admin_user = env.ref('base.user_admin', raise_if_not_found=False)
                if admin_user:
                    admin_user.write({'password': admin_password})
                    _logger.info(f"Password updated for user {admin_user.login}")
                cr.commit()

            _logger.info(f'Database {db_name} created successfully from template')
            return True

        except UserError:
            raise
        except Exception as e:
            _logger.error(f'Database creation failed for {db_name}: {str(e)}')
            raise UserError(_('Database creation failed: %s') % str(e))
    
    @api.model
    def delete_database(self, db_name, backup=True):
        """
        Delete a SaaS tenant database.
        
        Uses Odoo's internal _drop_database directly,
        bypassing exp_drop which is blocked when list_db=False.
        """
        try:
            _logger.info(f'Deleting database: {db_name}')

            # Check existence without using the blocked exp_db_exist
            if not self._db_exists_direct(db_name):
                _logger.warning(f'Database {db_name} does not exist')
                return True

            # Create backup if requested
            backup_path = None
            if backup:
                backup_path = self._backup_database(db_name)

            # Use Odoo's native drop, temporarily bypassing list_db=False
            import odoo
            
            original_list_db = odoo.tools.config.get('list_db')
            odoo.tools.config['list_db'] = True
            try:
                odoo.service.db.exp_drop(db_name)
            finally:
                odoo.tools.config['list_db'] = original_list_db

            _logger.info(f'Database {db_name} deleted successfully')
            return backup_path

        except UserError:
            raise
        except Exception as e:
            _logger.error(f'Database deletion failed for {db_name}: {str(e)}')
            raise UserError(_('Database deletion failed: %s') % str(e))
    
    @api.model
    def _backup_database(self, db_name):
        """Create database backup"""
        try:
            from datetime import datetime
            from odoo.service import db
            
            # Generate backup filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_filename = f'{db_name}_{timestamp}.dump'
            
            # Get backup directory from config
            backup_dir = self.env['ir.config_parameter'].sudo().get_param(
                'saas.backup_directory',
                '/tmp/odoo_backups'
            )
            
            # Create backup directory if it doesn't exist
            os.makedirs(backup_dir, exist_ok=True)
            
            backup_path = os.path.join(backup_dir, backup_filename)
            
            # Create backup using System's service
            with open(backup_path, 'wb') as backup_file:
                db.exp_dump(db_name, backup_file)
            
            _logger.info(f'Backup created: {backup_path}')
            return backup_path
            
        except Exception as e:
            _logger.error(f'Backup failed for {db_name}: {str(e)}')
            # Don't fail the whole operation if backup fails
            return None
    
    @api.model
    def install_modules(self, db_name, module_list):
        """
        Install modules in a specific database
        """
        try:
            _logger.info(f'Installing modules {module_list} in database {db_name}')
            
            import odoo
            registry = odoo.registry(db_name)
            
            # Switch to target database context
            with registry.cursor() as cr:
                env = api.Environment(cr, odoo.SUPERUSER_ID, {})
                
                # PREVENT ODOO AUTO-INSTALL MADNESS:
                # Odoo tries to install all localizations (l10n_*) when account is installed without a country.
                # Forcefully disable auto_install for all localizations not explicitly requested.
                l10n_modules = env['ir.module.module'].search([
                    ('name', '=like', 'l10n_%'),
                    ('state', '=', 'uninstalled'),
                    ('name', 'not in', module_list)
                ])
                if l10n_modules:
                    l10n_modules.write({'auto_install': False})
                    _logger.info(f"Disabled auto-install for {len(l10n_modules)} unwanted localization modules.")
                
                # --- INSTALL SPANISH LANGUAGE AND SET AS DEFAULT ---
                try:
                    lang = env['res.lang'].with_context(active_test=False).search([('code', '=', 'es_ES')], limit=1)
                    if lang:
                        lang.active = True
                        installer = env['base.language.install'].create({'lang_ids': [(6, 0, lang.ids)]})
                        installer.lang_install()
                        env['ir.config_parameter'].sudo().set_param('base.lang', 'es_ES')
                        
                        # Set it as default for admin and company
                        env.company.partner_id.lang = 'es_ES'
                        admin_user = env.ref('base.user_admin', raise_if_not_found=False)
                        if admin_user:
                            admin_user.lang = 'es_ES'
                            admin_user.partner_id.lang = 'es_ES'
                            
                        _logger.info("Spanish language installed and set as default.")
                except Exception as e:
                    _logger.warning(f"Could not install Spanish language: {e}")
                
                # Install any extra add-ons (like AI) that weren't in the template
                modules = env['ir.module.module'].search([
                    ('name', 'in', module_list),
                    ('state', '=', 'uninstalled')
                ])
                
                if modules:
                    _logger.info(f'Installing {len(modules)} add-on modules...')
                    modules.button_immediate_install()
                    _logger.info(f'Successfully installed add-ons in {db_name}')
                else:
                    _logger.info(f'All required modules were already installed via the template.')
            
            return True
            
        except Exception as e:
            _logger.error(f'Module installation failed in {db_name}: {str(e)}')
            # Don't fail provisioning if module installation fails
            return False
