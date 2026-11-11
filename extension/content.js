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

// A native alert, confirm or prompt blocks the page and nothing in an
// extension can answer it, so while handling is on the page's own functions are
// replaced: they record the dialog and answer it as the client chose. This lasts
// until the page navigates, which discards the replacements.
const DIALOG_LOG_LIMIT = 100;
const dialogState = { mode: 'off', promptText: null, log: [], originals: null };

function setDialogHandling(mode, promptText) {
  const page = window.wrappedJSObject;
  dialogState.promptText = promptText ?? null;
  if (mode === 'off') {
    if (dialogState.originals) {
      page.alert = dialogState.originals.alert;
      page.confirm = dialogState.originals.confirm;
      page.prompt = dialogState.originals.prompt;
      dialogState.originals = null;
    }
    dialogState.mode = 'off';
    return;
  }
  dialogState.mode = mode;
  if (dialogState.originals) {
    return;
  }
  dialogState.originals = { alert: page.alert, confirm: page.confirm, prompt: page.prompt };
  // A page that opens dialogs in a loop must not fill the log without end.
  const record = (type, message, extra) => {
    dialogState.log.push({ type, message: String(message).slice(0, 1000),
      accepted: dialogState.mode === 'accept', ...extra });
    if (dialogState.log.length > DIALOG_LOG_LIMIT) dialogState.log.shift();
  };
  page.alert = exportFunction(function (message) {
    record('alert', message);
  }, window);
  page.confirm = exportFunction(function (message) {
    record('confirm', message);
    return dialogState.mode === 'accept';
  }, window);
  page.prompt = exportFunction(function (message, fallback) {
    record('prompt', message, { default: String(fallback ?? '') });
    return dialogState.mode === 'accept' ? (dialogState.promptText ?? String(fallback ?? '')) : null;
  }, window);
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

      case 'dialogs': {
        if (!['accept', 'dismiss', 'off', 'log'].includes(data.mode)) {
          sendResponse({ error: 'content.dialogs needs a mode of accept, dismiss, off or log' });
          break;
        }
        if (data.mode !== 'log') {
          setDialogHandling(data.mode, data.promptText);
        }
        const log = dialogState.log.splice(0);
        sendResponse({ mode: dialogState.mode, dialogs: log });
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
