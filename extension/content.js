// Content script for page interaction
console.log('FoxMCP content script loaded');

// Listen for messages from background script
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  const { action, script } = request;
  
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
        
      default:
        sendResponse({ error: `Unknown content action: ${action}` });
    }
  } catch (error) {
    sendResponse({ error: error.message });
  }
  
  return true; // Keep message channel open for async response
});