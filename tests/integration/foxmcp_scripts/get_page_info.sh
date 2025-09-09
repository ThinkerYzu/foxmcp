#!/bin/bash
# Script that generates JavaScript to get page information
# Arguments: $1 = info type (title, url, text, etc.)

info_type="${1:-title}"

case "$info_type" in
    "title")
        echo "document.title"
        ;;
    "url")
        echo "window.location.href"
        ;;
    "text")
        echo "document.body.innerText.substring(0, 500)"
        ;;
    "links")
        echo "Array.from(document.links).map(a => a.href).slice(0, 10).join('\\n')"
        ;;
    *)
        echo "console.log('Unknown info type: $info_type'); 'Error: unknown info type'"
        ;;
esac