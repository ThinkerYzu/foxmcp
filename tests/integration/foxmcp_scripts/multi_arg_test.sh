#!/bin/bash
# Test script that demonstrates handling multiple arguments including those with spaces
# Arguments: $1 = message, $2 = element_id, $3 = color (optional)

message="${1:-Hello World}"
element_id="${2:-body}"
color="${3:-blue}"

# Generate JavaScript that creates or modifies an element with the message
cat << EOF
(function() {
    var element = document.getElementById('${element_id}') || document.body;
    var div = document.createElement('div');
    div.innerHTML = '${message}';
    div.style.color = '${color}';
    div.style.fontSize = '16px';
    div.style.margin = '10px';
    element.appendChild(div);
    return 'Added message: "${message}" to ${element_id} in ${color}';
})()
EOF