/*
 * FoxMCP Firefox Extension - Content Script
 * Copyright (c) 2024 FoxMCP Project
 * Licensed under the MIT License - see LICENSE file for details
 */

// Content script for page interaction
console.log('FoxMCP content script loaded');

function expireFileHandle(handles, fileId, delay) {
  setTimeout(() => handles.delete(fileId), delay);
}

// The page's console output and uncaught errors, kept from the moment a client
// first asks. Wrapping console on every page from the start would change stack
// locations and cost time for pages nobody is debugging, so it waits to be asked.
const CONSOLE_LIMIT = 500;
const consoleState = { armed: false, entries: [] };

function formatConsoleArg(value) {
  if (value === undefined) return 'undefined';
  if (value === null || typeof value !== 'object') return String(value);
  try {
    if (value instanceof window.wrappedJSObject.Error) return value.stack || String(value);
    return JSON.stringify(value);
  } catch (error) {
    return Object.prototype.toString.call(value);
  }
}

function addConsoleEntry(level, message) {
  consoleState.entries.push({ level, message: message.slice(0, 2000) });
  if (consoleState.entries.length > CONSOLE_LIMIT) consoleState.entries.shift();
}

function armConsole() {
  if (consoleState.armed) return;
  consoleState.armed = true;
  const page = window.wrappedJSObject;
  for (const level of ['log', 'info', 'warn', 'error', 'debug']) {
    const original = page.console[level];
    if (typeof original !== 'function') continue;
    // A page that froze or replaced console methods must not stop the others from being wrapped.
    try {
      page.console[level] = exportFunction(function (...args) {
        addConsoleEntry(level, args.map(formatConsoleArg).join(' '));
        // Spread, not apply(this, args): the array belongs to this script's side, and
        // the page's console cannot read it ("Permission denied to access property
        // length"), which would make every logged call throw in the page.
        return original.call(this || page.console, ...args);
      }, window);
    } catch (wrapError) {
      // Left as the page had it; its entries just are not recorded.
    }
  }
  window.addEventListener('error', event => addConsoleEntry('uncaught',
    `${event.message} (${event.filename}:${event.lineno}:${event.colno})`));
  window.addEventListener('unhandledrejection', event => addConsoleEntry('uncaught',
    'Unhandled promise rejection: ' + formatConsoleArg(event.reason)));
}

// Listen for messages from background script
browser.runtime.onMessage.addListener((request, sender, sendResponse) => {
  const { action, script, data } = request;

  console.log('📨 Content script received message:', action,
    action === 'storeFile' ? { fileId: data.fileId } : data);

  try {
    switch (action) {
      case 'prepareFile': {
        const fileId = data.fileId;
        const pending = globalThis.foxmcpPendingFiles ||= new Set();
        pending.add(fileId);
        expireFileHandle(pending, fileId, 120000);
        sendResponse({ ready: true });
        break;
      }

      case 'storeFile': {
        const fileId = data.fileId;
        if (!globalThis.foxmcpPendingFiles?.delete(fileId)) {
          throw new Error('Target document changed or the file load expired');
        }
        const files = globalThis.foxmcpFiles ||= new Map();
        files.set(fileId, data.file);
        expireFileHandle(files, fileId, 300000);
        sendResponse({ fileId });
        break;
      }

      case 'extractText':
        sendResponse({ text: document.body.innerText });
        break;

      case 'extractHTML':
        sendResponse({ html: document.documentElement.outerHTML });
        break;

      case 'getPageTitle':
        sendResponse({ title: document.title });
        break;

      case 'getPageURL':
        sendResponse({ url: window.location.href });
        break;

      case 'executeScript':
        try {
          const result = eval(script);
          sendResponse({ result });
        } catch (error) {
          sendResponse({ error: error.message });
        }
        break;

      case 'console': {
        if ((data.level != null && typeof data.level !== 'string') ||
            (data.pattern != null && typeof data.pattern !== 'string') ||
            (data.limit != null && !(Number.isInteger(data.limit) && data.limit >= 1 && data.limit <= 500))) {
          sendResponse({ error: 'content.console needs a string level and pattern and an integer limit from 1 to 500' });
          break;
        }
        const wasArmed = consoleState.armed;
        armConsole();
        let entries = consoleState.entries.filter(entry =>
          (!data.level || entry.level === data.level || (data.level === 'error' && entry.level === 'uncaught'))
          && (!data.pattern || entry.message.includes(data.pattern)));
        entries = entries.slice(-(data.limit || 50));
        if (data.clear) consoleState.entries.length = 0;
        sendResponse({ started: !wasArmed, entries });
        break;
      }

      default:
        sendResponse({ error: `Unknown content action: ${action}` });
    }
  } catch (error) {
    sendResponse({ error: error.message });
  }

  return true; // Keep message channel open for async response
});
