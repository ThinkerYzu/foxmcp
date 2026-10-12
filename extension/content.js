/*
 * FoxMCP Firefox Extension - Content Script
 * Copyright (c) 2024 FoxMCP Project
 * Licensed under the MIT License - see LICENSE file for details
 */

// Content script for page interaction
console.log('FoxMCP content script loaded');

// Elements a snapshot lists. Anything clickable or editable, plus headings so
// the listing reads as an outline of the page rather than a bag of controls.
const INTERACTIVE_SELECTOR = [
  'a[href]', 'button', 'input', 'select', 'textarea', 'summary', 'label',
  '[role=button]', '[role=link]', '[role=checkbox]', '[role=radio]', '[role=switch]',
  '[role=tab]', '[role=menuitem]', '[role=option]', '[role=combobox]', '[role=textbox]',
  '[role=row]', '[contenteditable=""]', '[contenteditable=true]', '[tabindex]:not([tabindex="-1"])',
  'h1', 'h2', 'h3'
].join(',');

const REF_ATTR = 'data-foxmcp-ref';
let nextRef = 1;

function isVisible(el) {
  const rect = el.getBoundingClientRect();
  if (rect.width === 0 || rect.height === 0) {
    return false;
  }
  const style = getComputedStyle(el);
  return style.visibility !== 'hidden' && style.display !== 'none' && style.opacity !== '0';
}

// A ref stays on its element across snapshots, so a ref read from one
// snapshot still works after the page re-renders other parts of itself.
function refFor(el) {
  let ref = el.getAttribute(REF_ATTR);
  if (!ref) {
    ref = 'r' + nextRef++;
    el.setAttribute(REF_ATTR, ref);
  }
  return ref;
}

function describe(el) {
  const role = el.getAttribute('role') || el.tagName.toLowerCase();
  const name = (el.getAttribute('aria-label') || el.innerText || el.value || el.placeholder ||
    el.title || el.alt || '').replace(/\s+/g, ' ').trim().slice(0, 80);
  const extras = [];
  if (el.type && el.tagName === 'INPUT') extras.push('type=' + el.type);
  if (el.disabled) extras.push('disabled');
  if (el.checked) extras.push('checked');
  if (el.getAttribute('aria-selected') === 'true') extras.push('selected');
  return `[${refFor(el)}] ${role} "${name}"${extras.length ? ' (' + extras.join(', ') + ')' : ''}`;
}

function snapshot(maxElements) {
  const lines = [];
  for (const el of document.querySelectorAll(INTERACTIVE_SELECTOR)) {
    if (!isVisible(el)) continue;
    lines.push(describe(el));
    if (lines.length >= maxElements) {
      lines.push(`... truncated at ${maxElements} elements`);
      break;
    }
  }
  return lines.join('\n');
}

function findTarget({ ref, selector }) {
  const el = ref
    ? document.querySelector(`[${REF_ATTR}="${CSS.escape(ref)}"]`)
    : document.querySelector(selector);
  if (!el) {
    throw new Error(ref ? `No element with ref ${ref}; take a new snapshot` : `No element matches ${selector}`);
  }
  return el;
}

// Sites listen on pointerdown or mousedown as often as on click (Google Drive's
// menus open on mousedown), so the whole sequence is dispatched at the element's
// centre rather than calling el.click().
function clickElement(el) {
  el.scrollIntoView({ block: 'center', inline: 'center' });
  const rect = el.getBoundingClientRect();
  const init = {
    bubbles: true, cancelable: true, composed: true, view: window, button: 0,
    clientX: rect.left + rect.width / 2, clientY: rect.top + rect.height / 2
  };
  el.dispatchEvent(new PointerEvent('pointerover', init));
  el.dispatchEvent(new MouseEvent('mouseover', init));
  el.dispatchEvent(new PointerEvent('pointerdown', { ...init, buttons: 1 }));
  el.dispatchEvent(new MouseEvent('mousedown', { ...init, buttons: 1 }));
  if (typeof el.focus === 'function') el.focus();
  el.dispatchEvent(new PointerEvent('pointerup', init));
  el.dispatchEvent(new MouseEvent('mouseup', init));
  el.dispatchEvent(new MouseEvent('click', init));
}

// insertText goes through the editor's own input path, so frameworks that track
// value through input events (React, Vue) see the change. Setting .value directly
// is the fallback for inputs where the command is refused.
function typeInto(el, text, clear) {
  el.scrollIntoView({ block: 'center' });
  el.focus();
  if (clear) {
    if (el.isContentEditable) {
      document.execCommand('selectAll');
    } else if (typeof el.select === 'function') {
      el.select();
    }
  }
  if (document.execCommand('insertText', false, text)) {
    return;
  }
  const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
  setter.call(el, clear ? text : el.value + text);
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
}

function pressKey(el, key) {
  const init = { key, bubbles: true, cancelable: true, composed: true };
  const notCancelled = el.dispatchEvent(new KeyboardEvent('keydown', init));
  el.dispatchEvent(new KeyboardEvent('keyup', init));
  // A synthetic Enter does not submit a form, so do what the browser would.
  if (key === 'Enter' && notCancelled && el.form && el.tagName !== 'TEXTAREA') {
    el.form.requestSubmit();
  }
}

// Listen for messages from background script
browser.runtime.onMessage.addListener((request, sender, sendResponse) => {
  const { action, script, data } = request;

  console.log('📨 Content script received message:', action, data);

  try {
    switch (action) {
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

      case 'snapshot':
        sendResponse({ snapshot: snapshot(data.maxElements || 300), url: location.href, title: document.title });
        break;

      case 'click': {
        const el = findTarget(data);
        clickElement(el);
        sendResponse({ clicked: describe(el) });
        break;
      }

      case 'type': {
        const el = findTarget(data);
        typeInto(el, data.text, data.clear !== false);
        if (data.submit) pressKey(el, 'Enter');
        sendResponse({ typed: describe(el) });
        break;
      }

      case 'pressKey': {
        const el = data.ref || data.selector ? findTarget(data) : (document.activeElement || document.body);
        pressKey(el, data.key);
        sendResponse({ pressed: data.key });
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