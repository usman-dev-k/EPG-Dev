/** @odoo-module **/

import { Component, useState, onMounted, xml } from "@odoo/owl";
import { useService, useBus } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { Dialog } from "@web/core/dialog/dialog";

class VideoDialog extends Component {
    static template = xml`
        <Dialog title="'Video Tutorial'" size="'lg'">
            <div style="width: 100%; aspect-ratio: 16 / 9;">
                <iframe t-att-src="props.videoUrl" allow="autoplay; encrypted-media" allowfullscreen="1" frameborder="0" style="width:100%; height:100%;"></iframe>
            </div>
        </Dialog>
    `;
    static components = { Dialog };
}

export class VideoTutorialSystray extends Component {
    setup() {
        this.menuService = useService("menu");
        this.dialogService = useService("dialog");
        this.state = useState({ tick: 0 });
        
        // Listen to URL changes natively in Odoo
        useBus(this.env.bus, "ROUTE_CHANGE", () => {
            this.state.tick++;
        });
        
        onMounted(() => {
            let attempts = 0;
            const interval = setInterval(() => {
                this.state.tick++;
                attempts++;
                if (attempts > 10 || this.menuService.getCurrentApp()) {
                    clearInterval(interval);
                }
            }, 500);
        });
    }

    get currentAppVideo() {
        // Access state.tick to ensure Owl tracks it as a dependency for re-rendering
        const _trigger = this.state.tick;
        const currentApp = this.menuService.getCurrentApp();
        if (!currentApp) return null;
        
        const xmlid = (currentApp.xmlid || '').toLowerCase();
        const name = (currentApp.name || '').toLowerCase();

        // Fuzzy matching to ensure we catch the correct app regardless of translation or custom XML IDs
        if (xmlid.includes('base_setup') || name.includes('settings') || name.includes('ajuste')) {
            return {
                'en': 'https://youtu.be/1qerqEWq9Ts?si=67gT8Iw2JzCxIuDe',
                'es': 'https://youtu.be/pAPDDab1c8E?si=rWOXpPY7MrHg5QvM'
            };
        }
        if (xmlid.includes('sale') || name.includes('sale') || name.includes('venta')) {
            return {
                'en': 'https://youtu.be/QVZW-1Fq3p8?si=oHHThXdZosgwGi1U',
                'es': 'https://youtu.be/7X6dKUsBUQA?si=3T_FGecoOrxUBDNt'
            };
        }
        if (xmlid.includes('crm') || name.includes('crm') || name.includes('fujo')) {
            return {
                'en': 'https://youtu.be/t9etMxFIlvM?si=UCQV6wRCIwsdkJmV',
                'es': 'https://youtu.be/-ISd_42GlOo?si=06H0wtKGS8Q95ofs'
            };
        }
        if (xmlid.includes('document') || name.includes('document')) {
            return {
                'en': 'https://youtu.be/vq4oL9jZvRw?si=vCHKgqNoNCyyLe5i',
                'es': 'https://youtu.be/BUSkqDMWZzI?si=2ZjI1C6es9c3n65S'
            };
        }
        if (xmlid.includes('board') || name.includes('dashboard') || name.includes('tablero')) {
            return {
                'en': 'https://youtu.be/-GCIGDN6HvQ?si=DlK-UjMzItCAehL0',
                'es': 'https://youtu.be/ZPJnHJXpxNo?si=maQiiOqb56to9ga0'
            };
        }
        if (xmlid.includes('contact') || name.includes('contact')) {
            return {
                'en': 'https://youtu.be/PyCsLvbiCWM?si=5UJ1WGsbUFuWDh6O',
                'es': 'https://youtu.be/DHzvmNPsN_U?si=gqIGM4t2w5XkT8Nk'
            };
        }
        if (xmlid.includes('ai') || name.includes('ai') || name.includes('assistant') || name.includes('inteligencia') || name.includes('robot')) {
            return {
                'en': 'https://youtu.be/Hzkyzx9Jzk8?si=ZjVWHb6t-OJaSZO0',
                'es': 'https://youtu.be/JZjbb-0Cq6I?si=R_CVW8q8R-Qw8JCv'
            };
        }
        if (xmlid.includes('account') || name.includes('account') || name.includes('contabilidad') || name.includes('finance') || name.includes('facturaci')) {
            return {
                'en': 'https://youtu.be/tSj9QFVUt2k?si=fJdd2QI2yUpcMFOP',
                'es': 'https://youtu.be/iEFSQXn1rUA?si=O8bfE7F-6Z0lpFTG'
            };
        }
        
        return null;
    }

    get isVisible() {
        return this.currentAppVideo !== null;
    }

    openVideo(lang) {
        const video = this.currentAppVideo;
        if (video && video[lang]) {
            const url = video[lang];
            // Convert youtu.be link to embed link
            let videoId = '';
            if (url.includes('youtu.be/')) {
                videoId = url.split('youtu.be/')[1].split('?')[0];
            } else if (url.includes('youtube.com/watch?v=')) {
                videoId = url.split('v=')[1].split('&')[0];
            }
            
            if (videoId) {
                const embedUrl = `https://www.youtube.com/embed/${videoId}?autoplay=1`;
                this.dialogService.add(VideoDialog, { videoUrl: embedUrl });
            } else {
                window.open(url, '_blank');
            }
        }
    }
}

VideoTutorialSystray.template = "saas_client.VideoTutorialSystray";

export const systrayItem = {
    Component: VideoTutorialSystray,
    isDisplayed: (env) => true,
};

registry.category("systray").add("VideoTutorialSystray", systrayItem, { sequence: 98 });
