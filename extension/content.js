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
// centre rather than calling el.click(). A double click repeats the sequence
// with the click count in `detail` and ends with dblclick, which is what opens
// a folder in Google Drive; a lone dblclick event is ignored there.
function clickElement(el, clicks = 1) {
  el.scrollIntoView({ block: 'center', inline: 'center' });
  const rect = el.getBoundingClientRect();
  const init = {
    bubbles: true, cancelable: true, composed: true, view: window, button: 0,
    clientX: rect.left + rect.width / 2, clientY: rect.top + rect.height / 2
  };
  el.dispatchEvent(new PointerEvent('pointerover', init));
  el.dispatchEvent(new MouseEvent('mouseover', init));
  for (let detail = 1; detail <= clicks; detail++) {
    el.dispatchEvent(new PointerEvent('pointerdown', { ...init, detail, buttons: 1 }));
    el.dispatchEvent(new MouseEvent('mousedown', { ...init, detail, buttons: 1 }));
    if (typeof el.focus === 'function') el.focus();
    el.dispatchEvent(new PointerEvent('pointerup', { ...init, detail }));
    el.dispatchEvent(new MouseEvent('mouseup', { ...init, detail }));
    el.dispatchEvent(new MouseEvent('click', { ...init, detail }));
  }
  if (clicks === 2) {
    el.dispatchEvent(new MouseEvent('dblclick', { ...init, detail: 2 }));
  }
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

// Many sites (Google Drive among them) open the file dialog by calling click()
// on an <input type=file> they create on the spot, and a native dialog is not
// something an extension can fill in. While armed, this swaps the page's own
// click() and showPicker() so the next file input is handed back here instead
// of opening the dialog. It goes through wrappedJSObject because the page's
// prototypes are invisible from the content script's side.
function captureNextFileInput(timeoutMs) {
  const proto = window.wrappedJSObject.HTMLInputElement.prototype;
  const originalClick = proto.click;
  const originalShowPicker = proto.showPicker;
  return new Promise((resolve, reject) => {
    const restore = () => {
      proto.click = originalClick;
      proto.showPicker = originalShowPicker;
    };
    const timer = setTimeout(() => {
      restore();
      reject(new Error('The trigger did not open a file dialog'));
    }, timeoutMs);
    const intercept = exportFunction(function () {
      if (this.type !== 'file') {
        return originalClick.call(this);
      }
      clearTimeout(timer);
      restore();
      // Inputs created just for the dialog are often never attached, and a
      // detached element cannot be found again by ref.
      if (!this.isConnected) {
        this.hidden = true;
        document.body.appendChild(this);
      }
      resolve(this);
    }, window);
    proto.click = intercept;
    proto.showPicker = intercept;
  });
}

// webkitRelativePath is what tells a page the files came from a folder (and
// which subfolder each sits in), so it is set where the page reads it.
function setInputFiles(el, files, relativePaths) {
  if (el.tagName !== 'INPUT' || el.type !== 'file') {
    throw new Error('Target must be an <input type=file>');
  }
  // Files built in the extension belong to it, and the page gets "Permission
  // denied" reading them. Cloned into the page and set through the page's own
  // DataTransfer, they are ordinary files as far as the page can tell.
  const transfer = new window.wrappedJSObject.DataTransfer();
  for (const file of files) {
    transfer.items.add(cloneInto(file, window));
  }
  el.wrappedJSObject.files = transfer.files;
  const pageFiles = el.wrappedJSObject.files;
  // A browser only reports folder paths for inputs that pick folders, so a
  // folder given to a plain file input arrives as loose files, as it would.
  for (let i = 0; i < pageFiles.length; i++) {
    if (el.webkitdirectory && relativePaths[i]) {
      Object.defineProperty(pageFiles[i], 'webkitRelativePath', {
        value: relativePaths[i], configurable: true
      });
    }
  }
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
  return Array.from({ length: pageFiles.length },
    (_, i) => pageFiles[i].webkitRelativePath || pageFiles[i].name);
}

// Overlay shown while an agent acts on the tab: a glowing border, a label and a
// cursor that moves to each element before it is clicked or typed into. It is
// purely visual (pointer-events: none) and fades once the agent goes quiet, so
// the tab looks normal again when the person takes over.
const OVERLAY_ID = 'foxmcp-agent-overlay';
const OVERLAY_IDLE_MS = 6000;
const CURSOR_MOVE_MS = 350;
let overlayTimer = null;
let cursorPos = null;

function overlayRoot() {
  let host = document.getElementById(OVERLAY_ID);
  if (!host) {
    host = document.createElement('div');
    host.id = OVERLAY_ID;
    host.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:2147483647;';
    const root = host.attachShadow({ mode: 'open' });
    root.innerHTML = `
      <style>
        :host { transition: opacity .4s; }
        .glow { position:fixed; inset:0; box-shadow: inset 0 0 0 2px rgba(217,119,87,.9), inset 0 0 22px rgba(217,119,87,.5); }
        .label { position:fixed; left:50%; bottom:14px; transform:translateX(-50%); display:flex; align-items:center; gap:8px;
          padding:7px 14px; border-radius:999px; background:rgba(28,25,23,.92); color:#fff;
          font:500 13px/1 system-ui, sans-serif; box-shadow:0 2px 10px rgba(0,0,0,.3); white-space:nowrap; }
        .dot { width:8px; height:8px; border-radius:50%; background:rgb(217,119,87); }
        .cursor { position:fixed; left:0; top:0; width:22px; height:22px; opacity:0; filter:drop-shadow(0 1px 2px rgba(0,0,0,.45)); }
        .ripple { position:fixed; width:28px; height:28px; margin:-14px 0 0 -14px; border-radius:50%;
          border:2px solid rgb(217,119,87); animation:ripple .45s ease-out forwards; }
        @keyframes ripple { from { transform:scale(.3); opacity:1; } to { transform:scale(1.4); opacity:0; } }
      </style>
      <div class="glow"></div>
      <div class="label"><span class="dot"></span>AI agent is working in this tab</div>
      <svg class="cursor" viewBox="0 0 22 22" xmlns="http://www.w3.org/2000/svg">
        <path d="M2 1.5 L2 18 L6.6 13.9 L9.6 20.5 L12.5 19.2 L9.6 12.7 L15.8 12.7 Z" fill="rgb(217,119,87)" stroke="#fff" stroke-width="1.4" stroke-linejoin="round"/>
      </svg>`;
    document.documentElement.appendChild(host);
  }
  return host;
}

function showOverlay() {
  const host = overlayRoot();
  host.style.opacity = '1';
  host.style.visibility = 'visible';
  clearTimeout(overlayTimer);
  overlayTimer = setTimeout(() => { host.style.opacity = '0'; }, OVERLAY_IDLE_MS);
}

async function moveCursorTo(el, press) {
  el.scrollIntoView({ block: 'center', inline: 'center' });
  const rect = el.getBoundingClientRect();
  const to = { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
  const from = cursorPos || to;
  cursorPos = to;
  const root = overlayRoot().shadowRoot;
  const cursor = root.querySelector('.cursor');
  cursor.style.transition = 'none';
  cursor.style.opacity = '1';
  cursor.style.transform = `translate(${from.x}px, ${from.y}px)`;
  cursor.getBoundingClientRect();
  cursor.style.transition = `transform ${CURSOR_MOVE_MS}ms cubic-bezier(.3,.7,.4,1)`;
  cursor.style.transform = `translate(${to.x}px, ${to.y}px)`;
  await new Promise(resolve => setTimeout(resolve, CURSOR_MOVE_MS));
  if (press) {
    const ripple = document.createElement('div');
    ripple.className = 'ripple';
    ripple.style.left = to.x + 'px';
    ripple.style.top = to.y + 'px';
    root.appendChild(ripple);
    setTimeout(() => ripple.remove(), 500);
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
        showOverlay();
        sendResponse({ snapshot: snapshot(data.maxElements || 300), url: location.href, title: document.title });
        break;

      case 'click': {
        const el = findTarget(data);
        showOverlay();
        moveCursorTo(el, true)
          .then(() => {
            clickElement(el, data.doubleClick ? 2 : 1);
            sendResponse({ clicked: describe(el) });
          })
          .catch(error => sendResponse({ error: error.message }));
        break;
      }

      case 'type': {
        const el = findTarget(data);
        showOverlay();
        moveCursorTo(el, true)
          .then(() => {
            typeInto(el, data.text, data.clear !== false);
            if (data.submit) pressKey(el, 'Enter');
            sendResponse({ typed: describe(el) });
          })
          .catch(error => sendResponse({ error: error.message }));
        break;
      }

      case 'pressKey': {
        const el = data.ref || data.selector ? findTarget(data) : (document.activeElement || document.body);
        showOverlay();
        pressKey(el, data.key);
        sendResponse({ pressed: data.key });
        break;
      }

      case 'captureFileInput': {
        const trigger = findTarget({ ref: data.triggerRef, selector: data.triggerSelector });
        showOverlay();
        const captured = captureNextFileInput(data.timeoutMs || 3000);
        moveCursorTo(trigger, true)
          .then(() => clickElement(trigger))
          .then(() => captured)
          .then(input => sendResponse({ ref: refFor(input), multiple: input.multiple, directory: input.webkitdirectory }))
          .catch(error => sendResponse({ error: error.message }));
        break;
      }

      case 'setFiles': {
        const el = findTarget(data);
        showOverlay();
        const paths = setInputFiles(el, data.files, data.relativePaths || []);
        sendResponse({ count: paths.length, paths: paths.slice(0, 5), target: describe(el) });
        break;
      }

      // Hidden while a screenshot is taken, so the capture shows the page as
      // it is rather than with the agent's border and cursor on top.
      case 'overlayVisibility': {
        const host = document.getElementById(OVERLAY_ID);
        if (host) host.style.visibility = data.visible ? 'visible' : 'hidden';
        sendResponse({ ok: true });
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