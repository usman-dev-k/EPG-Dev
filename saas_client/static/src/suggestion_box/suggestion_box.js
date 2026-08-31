/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { rpc } from "@web/core/network/rpc";

export class SuggestionBox extends Component {
    static template = "saas_client.SuggestionBox";

    setup() {
        this.notification = useService("notification");
        this.state = useState({
            isOpen: false,
            suggestionText: "",
            isSubmitting: false,
        });
    }

    toggleBox() {
        this.state.isOpen = !this.state.isOpen;
    }

    async submitSuggestion() {
        if (!this.state.suggestionText.trim()) {
            this.notification.add("Por favor escriba una sugerencia.", { type: "warning" });
            return;
        }

        this.state.isSubmitting = true;

        try {
            // We need to fetch main url from saas_client settings.
            // But we can also just make an RPC to a local controller, which then forwards to the main DB.
            // Let's create a local controller that will use the saas.client config to send the data.
            const result = await rpc("/saas_client/submit_suggestion", {
                suggestion: this.state.suggestionText,
            });

            if (result.status === 'success') {
                this.notification.add("Sugerencia enviada correctamente. ¡Gracias!", { type: "success" });
                this.state.suggestionText = "";
                this.state.isOpen = false;
            } else {
                this.notification.add("Error al enviar la sugerencia: " + (result.message || "Desconocido"), { type: "danger" });
            }
        } catch (error) {
            console.error(error);
            this.notification.add("Error de conexión al enviar sugerencia.", { type: "danger" });
        } finally {
            this.state.isSubmitting = false;
        }
    }
}

// Add it to the main webclient layout
registry.category("main_components").add("saas_client.SuggestionBox", {
    Component: SuggestionBox,
});
