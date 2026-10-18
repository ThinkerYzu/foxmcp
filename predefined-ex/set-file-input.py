#!/usr/bin/env python3
# foxmcp-description: Assign a file loaded by content_load_file to a page's file input and release its handle
# foxmcp-args: [file_id, CSS selector]

import json
import sys

if len(sys.argv) != 3:
    sys.exit("Usage: set-file-input.py FILE_ID CSS_SELECTOR")

args = json.dumps(sys.argv[1:])
sys.stdout.write("""(() => {
  const [fileId, selector] = """ + args + """;
  const file = globalThis.foxmcpFiles?.get(fileId);
  if (!file) throw new Error('File handle expired or belongs to another tab');
  const input = document.querySelector(selector);
  if (!input || input.tagName !== 'INPUT' || input.type !== 'file') {
    throw new Error('Selector must match an input type=file');
  }
  const transfer = new window.wrappedJSObject.DataTransfer();
  transfer.items.add(cloneInto(file, window));
  input.wrappedJSObject.files = transfer.files;
  input.dispatchEvent(new Event('input', { bubbles: true }));
  input.dispatchEvent(new Event('change', { bubbles: true }));
  globalThis.foxmcpFiles.delete(fileId);
  return { name: file.name, type: file.type, size: file.size };
})()
""")
