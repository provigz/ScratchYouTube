// ==UserScript==
// @name         Scratch HTTP GET requests hack
// @namespace    https://github.com/provigz/ScratchYouTube
// @version      2026-08-24
// @description  A hack that allows Scratch projects to perform HTTP GET requests to a certain host, localhost by default. Used by the provigz/ScratchYouTube project.
// @author       provigz
// @match        https://scratch.mit.edu/projects/*
// @icon         https://www.google.com/s2/favicons?sz=64&domain=scratch.mit.edu
// @run-at       document-start
// @grant        unsafeWindow
// ==/UserScript==

const targetHost = "http://localhost";

(function() {
    'use strict';

    let hasConfirmedThisSession = false;

    const originalFetch = unsafeWindow.fetch;
    unsafeWindow.fetch = async function(req, options) {
        if (typeof req.url === "string")
        {
            if (req.url.startsWith("https://translate-service.scratch.mit.edu/translate") ||
                req.url.startsWith("https://synthesis-service.scratch.mit.edu/synth"))
            {
                const text = (new URLSearchParams(req.url)).get("text");
                if (text && text.startsWith("HTTP "))
                {
                    if (!hasConfirmedThisSession) {
                        const userApproved = unsafeWindow.confirm(
                            `The current Scratch project is requesting to connect to "${targetHost}" to fetch custom data.\n\nMAKE SURE YOU TRUST THIS PROJECT! Do you wish to proceed?`
                        );
                        if (userApproved) {
                            hasConfirmedThisSession = true;
                        } else {
                            return originalFetch(req, options);
                        }
                    }

                    // Proceed with the redirection if confirmed
                    if (req.url.includes("translate")) {
                        return originalFetch(`${targetHost}/translate?text=${text.substring(5)}`, options);
                    } else {
                        return originalFetch(`${targetHost}/synth?text=${text.substring(5)}`, options);
                    }
                }
            }
        }
        return originalFetch(req, options);
    };
})();
