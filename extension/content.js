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

      default:
        sendResponse({ error: `Unknown content action: ${action}` });
    }
  } catch (error) {
    sendResponse({ error: error.message });
  }

  return true; // Keep message channel open for async response
});
