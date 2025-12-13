// ==UserScript==
// @name         Scratch HTTP GET requests hack
// @namespace    https://github.com/provigz/ScratchYouTube
// @version      2025-12-13
// @description  A hack that allows Scratch projects to perform HTTP GET requests to a certain host. Used by the provigz/ScratchYouTube project.
// @author       provigz
// @match        https://scratch.mit.edu/projects/*
// @icon         https://www.google.com/s2/favicons?sz=64&domain=scratch.mit.edu
// @run-at       document-start
// @grant        unsafeWindow
// ==/UserScript==

const targetHost = "http://localhost";

(function() {
    'use strict';

    const originalFetch = unsafeWindow.fetch;
    unsafeWindow.fetch = async function(url, options) {
        if (typeof url === "string") {
            const text = (new URLSearchParams(url)).get("text")
            if (text.startsWith("HTTP ")) {
                if (url.startsWith("https://translate-service.scratch.mit.edu/translate")) {
                    return originalFetch(`${targetHost}/translate?text=${text.substring(5)}`, options);
                } else if (url.startsWith("https://synthesis-service.scratch.mit.edu/synth")) {
                    return originalFetch(`${targetHost}/synth?text=${text.substring(5)}`, options);
                }
            }
        }
        return originalFetch(url, options);
    };

})();
