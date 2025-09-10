#!/bin/bash
# Script that generates JavaScript to get page information
# Arguments: $1 = info type (title, url, text, etc.)

info_type="${1:-title}"

case "$info_type" in
    "title")
        echo "(function() { return document.title; })()"
        ;;
    "url")
        echo "(function() { return window.location.href; })()"
        ;;
    "text")
        echo "(function() { return document.body.innerText.substring(0, 500); })()"
        ;;
    "links")
        echo "(function() { return Array.from(document.links).map(a => a.href).slice(0, 10).join('\\n'); })()"
        ;;
    *)
        echo "(function() { console.log('Unknown info type: $info_type'); return 'Error: unknown info type'; })()"
        ;;
esac