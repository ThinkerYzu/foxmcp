# Predefined Scripts

Predefined scripts are external executable scripts that generate JavaScript code dynamically and execute it in browser tabs. This powerful feature allows you to create reusable, parameterized browser automation scripts that can be called via the `content_execute_predefined` MCP tool.

## How Predefined Scripts Work

1. **Script Execution**: External script runs with optional arguments
2. **JavaScript Generation**: Script outputs JavaScript code to stdout
3. **Browser Injection**: Generated JavaScript is executed in the specified browser tab
4. **Result Return**: Execution result is returned to the caller

## Creating Predefined Scripts

### 1. Setup Script Directory

Set the environment variable to point to your scripts directory:
```bash
export FOXMCP_EXT_SCRIPTS="/path/to/your/scripts"
```

### 2. Claude Code Integration

The `claude-ex/` directory contains CLAUDE.md templates that help Claude Code understand how to create predefined external scripts:

```bash
# Copy the template to enable Claude Code script assistance
cp claude-ex/CLAUDE.md.template CLAUDE.md
```

This template provides Claude Code with:
- Context about foxmcp predefined script system
- Examples of script creation patterns
- Guidelines for work-related browser automation
- Understanding of script argument handling

### 3. Create Executable Script

Scripts must be executable and output JavaScript to stdout:

**Simple Example** (`get_title.sh`):
```bash
#!/bin/bash
# Simple script that gets page title
echo "(function() { return document.title; })()"
```

**Parameterized Example** (`get_page_info.sh`):
```bash
#!/bin/bash
# Script that takes info type as argument
info_type="${1:-title}"
case "$info_type" in
  "title") echo "(function() { return document.title; })()" ;;
  "url") echo "(function() { return window.location.href; })()" ;;
  "text") echo "(function() { return document.body.innerText.substring(0, 500); })()" ;;
  *) echo "(function() { return document.title + ' - Unknown info type'; })()" ;;
esac
```

**Advanced Example** (`add_banner.sh`):
```bash
#!/bin/bash
# Script that adds a banner with custom message and color
message="${1:-Hello World!}"
color="${2:-blue}"
cat << EOF
(function() {
  const banner = document.createElement('div');
  banner.style.cssText = 'position:fixed;top:0;left:0;width:100%;background:${color};color:white;text-align:center;padding:10px;z-index:9999;';
  banner.textContent = '${message}';
  document.body.insertBefore(banner, document.body.firstChild);
  return 'Banner added: ${message}';
})()
EOF
```

### 4. Make Scripts Executable

```bash
chmod +x /path/to/your/scripts/*.sh
```

## Using Predefined Scripts

### Via MCP Tools

**No Arguments**:
```json
{
  "name": "content_execute_predefined",
  "arguments": {
    "tab_id": 123,
    "script_name": "get_title.sh",
    "script_args": ""
  }
}
```

**Single Argument**:
```json
{
  "name": "content_execute_predefined",
  "arguments": {
    "tab_id": 123,
    "script_name": "get_page_info.sh",
    "script_args": "[\"url\"]"
  }
}
```

**Multiple Arguments**:
```json
{
  "name": "content_execute_predefined",
  "arguments": {
    "tab_id": 123,
    "script_name": "add_banner.sh",
    "script_args": "[\"Welcome to our site!\", \"green\"]"
  }
}
```

### Via Claude Code

Once configured with Claude Code, you can use natural language:

```
User: "Add a red banner saying 'Under Maintenance' to the current page"
Claude: I'll add a maintenance banner to your page using a predefined script.
```

Claude Code will call:
```
content_execute_predefined(tab_id=current_tab, script_name="add_banner.sh", script_args=["Under Maintenance", "red"])
```

## Script Output Types

Predefined scripts output JavaScript code that gets executed in the browser tab. **Recommended practice** is to wrap code in an immediately invoked function expression (IIFE) for better isolation:

```bash
#!/bin/bash
# Simple value return (wrapped in IIFE for isolation)
echo "(function() { return document.title; })()"
```

```bash
#!/bin/bash
# Complex operations with return value
echo "(function() { return 'Script completed: ' + document.title; })()"
```

```bash
#!/bin/bash
# Execute actions and return status messages
echo "(function() { document.body.style.backgroundColor = 'lightblue'; return 'Background changed successfully'; })()"
```

**Benefits of IIFE pattern:**
- Prevents variable conflicts with page code
- Creates isolated scope for script execution
- Enables proper return value handling
- Follows JavaScript best practices

## Security Features

- ✅ **Path Traversal Protection**: Script names cannot contain `..`, `/`, or `\`
- ✅ **Character Validation**: Only alphanumeric, underscore, dash, and dot allowed
- ✅ **Directory Containment**: Scripts must be within `FOXMCP_EXT_SCRIPTS` directory
- ✅ **Executable Validation**: Scripts must have execute permissions
- ✅ **JSON Validation**: Arguments must be valid JSON array of strings
- ✅ **Timeout Protection**: Scripts timeout after 30 seconds

## Best Practices

1. **Error Handling**: Always include error handling in your scripts
2. **Validation**: Validate input arguments before using them
3. **Documentation**: Add comments explaining what your script does
4. **Testing**: Test scripts independently before using with FoxMCP
5. **Security**: Never accept untrusted input or execute dangerous commands

## Documenting Scripts for AI Tools

**Important**: When you create new predefined scripts, document them in your project's `CLAUDE.md` file so AI tools can discover and use them effectively.

**Add to your CLAUDE.md**:
```markdown
## Foxmcp Predefined External Scripts
- script_name.sh: Brief description of what the script does
  Usage: script_name.sh "arg1" "arg2"
  Example: script_name.sh "Get page title"
- another_script.sh: Another script description
  Usage: another_script.sh [optional_arg]
```

**Benefits**:
- AI tools automatically discover your custom scripts
- Enables natural language usage ("extract the page title" → calls your script)
- Provides usage examples for correct parameter formatting
- Maintains documentation alongside your codebase

## Example Script Collection

Create a collection of useful scripts:

**`dom-summarize.sh`** - Simplify DOM tree for AI agent understanding:
```bash
#!/bin/bash
# Simplifies complex DOM trees into a readable hierarchical structure showing
# only interactive elements that users see and interact with. This allows AI
# agents to easily understand page components without parsing full HTML.
#
# Features:
# - Extracts visible interactive elements (input, textarea, select, button, a, option)
# - Assigns persistent dsid attributes for future reference and interaction
# - Shows hierarchical nesting with indentation
# - Flattens non-interesting containers for clarity
#
# Arguments:
#   $1 - Optional: "onscreen" to filter only elements visible in viewport
#   $2 - Optional: "withpos" to include position/size (only with "onscreen")
# Usage:
#   dom-summarize.sh                    # All visible elements
#   dom-summarize.sh onscreen           # Only viewport-visible elements
#   dom-summarize.sh onscreen withpos   # With position info (x,y,width,height)
```
See `predefined-ex/dom-summarize.sh` for full implementation.

**`extract_links.sh`** - Extract all links from page:
```bash
#!/bin/bash
echo "(function() { return Array.from(document.links).map(link => ({text: link.textContent.trim(), url: link.href})).slice(0, 10); })()"
```

**`highlight_text.sh`** - Highlight text on page:
```bash
#!/bin/bash
search_text="${1:-example}"
cat << EOF
(function() {
  const searchText = '${search_text}';
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let node;
  const textNodes = [];
  while (node = walker.nextNode()) {
    if (node.textContent.toLowerCase().includes(searchText.toLowerCase())) {
      textNodes.push(node);
    }
  }
  textNodes.forEach(textNode => {
    const parent = textNode.parentNode;
    const wrapper = document.createElement('span');
    wrapper.style.backgroundColor = 'yellow';
    wrapper.textContent = textNode.textContent;
    parent.replaceChild(wrapper, textNode);
  });
  return 'Highlighted ' + textNodes.length + ' instances of "' + searchText + '"';
})()
EOF
```

**`count_elements.sh`** - Count specific elements:
```bash
#!/bin/bash
element_type="${1:-div}"
echo "(function() { return document.querySelectorAll('${element_type}').length + ' ${element_type} elements found'; })()"
```

## Advanced Features

### Error Handling in Scripts

```bash
#!/bin/bash
# Script with proper error handling
if [ -z "$1" ]; then
  echo "(function() { return 'Error: Missing required argument'; })()"
  exit 1
fi

search_term="$1"
cat << EOF
(function() {
  try {
    const elements = document.querySelectorAll('*');
    let count = 0;
    elements.forEach(el => {
      if (el.textContent.toLowerCase().includes('${search_term}'.toLowerCase())) {
        count++;
      }
    });
    return 'Found "' + '${search_term}' + '" in ' + count + ' elements';
  } catch (error) {
    return 'Script error: ' + error.message;
  }
})()
EOF
```

### Multi-language Support

Scripts can be written in any language as long as they output JavaScript:

**Python Example** (`analyze_page.py`):
```python
#!/usr/bin/env python3
import sys
import json

def generate_analysis_script():
    return """
(function() {
  const stats = {
    paragraphs: document.querySelectorAll('p').length,
    images: document.querySelectorAll('img').length,
    links: document.querySelectorAll('a').length,
    headings: document.querySelectorAll('h1,h2,h3,h4,h5,h6').length
  };
  return 'Page analysis: ' + JSON.stringify(stats);
})()
"""

if __name__ == "__main__":
    print(generate_analysis_script().strip())
```

## Testing Scripts

Test your scripts independently before using with FoxMCP:

```bash
# Test script output
./your_script.sh "test argument"

# Should output valid JavaScript
# Example output: (function() { return 'Hello test argument'; })()
```

## Troubleshooting

### Common Issues

1. **Script not found**: Check `FOXMCP_EXT_SCRIPTS` environment variable
2. **Permission denied**: Ensure script has execute permissions (`chmod +x script.sh`)
3. **Invalid JavaScript**: Test script output manually
4. **Timeout errors**: Optimize script for faster execution (< 30 seconds)
5. **Argument parsing**: Ensure arguments are properly escaped and validated

### Debug Mode

Enable debug logging to troubleshoot script execution:

```bash
# Server will log script execution details
python server/server.py --debug
```