// ==UserScript==
// @name         Scratch YouTube: HTTP hack
// @namespace    http://tampermonkey.net/
// @version      2025-12-05
// @description  try to take over the world!
// @author       provigz
// @match        https://scratch.mit.edu/projects/editor/*
// @icon         https://www.google.com/s2/favicons?sz=64&domain=scratch.mit.edu
// @run-at       document-start
// @grant        unsafeWindow
// ==/UserScript==

const targetHost = "http://localhost";

(function() {
    'use strict';

    const originalFetch = unsafeWindow.fetch;
    unsafeWindow.fetch = async function(url, init) {
        if (url.startsWith("https://translate-service.scratch.mit.edu/translate")) {
            return originalFetch(url.replace("https://translate-service.scratch.mit.edu", targetHost), init);
        } else if (url.startsWith("https://synthesis-service.scratch.mit.edu/synth")) {
            return originalFetch(url.replace("https://synthesis-service.scratch.mit.edu", targetHost), init);
        }
        return originalFetch(url, init);
    };

})();
