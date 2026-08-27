/** EPG POS Theme — Override browser page title to say "EPG POS" */
(function () {
    // Set on load
    document.title = "EPG POS";

    // Keep watching in case Odoo resets it
    const observer = new MutationObserver(() => {
        if (document.title !== "EPG POS") {
            document.title = "EPG POS";
        }
    });

    const titleEl = document.querySelector("title");
    if (titleEl) {
        observer.observe(titleEl, { childList: true });
    }
})();
