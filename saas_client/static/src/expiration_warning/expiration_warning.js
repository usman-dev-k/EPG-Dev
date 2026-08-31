/** @odoo-module **/

import { Component, useState, onMounted } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";

export class ExpirationWarningSystray extends Component {
    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            daysLeft: null,
            isVisible: false,
        });

        onMounted(async () => {
            await this.checkExpiration();
        });
    }

    async checkExpiration() {
        try {
            const expDateStr = await this.orm.call("ir.config_parameter", "get_param", ["saas.expiration_date"]);
            if (expDateStr && expDateStr !== "False") {
                // Parse date string (e.g. "2026-06-25 14:00:00")
                const expDate = new Date(expDateStr.replace(' ', 'T') + 'Z');
                const now = new Date();
                
                // Calculate difference in days
                const diffTime = expDate - now;
                const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
                
                if (diffDays <= 3 && diffDays > 0) {
                    this.state.daysLeft = diffDays;
                    this.state.isVisible = true;
                    
                    // Show a sticky popup notification if 1 day left
                    if (diffDays <= 1) {
                        this.notification.add(
                            _t("¡Tu período de prueba expira en menos de 1 día! Actualiza tu plan para evitar la suspensión de la base de datos."),
                            {
                                title: _t("Aviso Importante"),
                                type: "danger",
                                sticky: true,
                            }
                        );
                    }
                } else if (diffDays <= 0) {
                    this.state.daysLeft = 0;
                    this.state.isVisible = true;
                    this.notification.add(
                        _t("¡Tu período de prueba ha expirado! Tu base de datos será suspendida pronto."),
                        {
                            title: _t("Prueba Expirada"),
                            type: "danger",
                            sticky: true,
                        }
                    );
                }
            }
        } catch (error) {
            console.error("Failed to fetch expiration date", error);
        }
    }
}

ExpirationWarningSystray.template = "saas_client.ExpirationWarningSystray";

export const systrayItem = {
    Component: ExpirationWarningSystray,
    isDisplayed: (env) => true,
};

registry.category("systray").add("ExpirationWarningSystray", systrayItem, { sequence: 97 });
