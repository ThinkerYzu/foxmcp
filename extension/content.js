/*
 * FoxMCP Firefox Extension - Content Script
 * Copyright (c) 2024 FoxMCP Project
 * Licensed under the MIT License - see LICENSE file for details
 */

// Content script for page interaction
console.log('FoxMCP content script loaded');

// Response body capture state
let responseBodyCaptureEnabled = false;
let capturedResponses = new Map(); // requestId -> responseData
let monitorConfig = null;

// Store original fetch and XMLHttpRequest for restoration
const originalFetch = window.fetch;
const originalXMLHttpRequest = window.XMLHttpRequest;

// Generate request ID for correlation with background script
function generateRequestId(url, method) {
  return `req_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}

// Check if URL matches monitoring patterns
function urlMatchesPatterns(url, patterns) {
  if (!patterns || patterns.length === 0) return false;

  for (const pattern of patterns) {
    if (pattern === '*') return true;

    // Convert pattern to regex
    const regexPattern = pattern
      .replace(/\*/g, '.*')
      .replace(/\?/g, '\\?');

    try {
      const regex = new RegExp(regexPattern);
      if (regex.test(url)) return true;
    } catch (e) {
      // Fallback to simple string matching
      if (url.includes(pattern.replace(/\*/g, ''))) return true;
    }
  }

  return false;
}

// Check if content type should be captured
function shouldCaptureContentType(contentType, captureTypes) {
  if (!captureTypes || captureTypes.length === 0) return true;
  if (!contentType) return false;

  return captureTypes.some(type => {
    if (type.includes('*')) {
      const baseType = type.split('/')[0];
      return contentType.startsWith(baseType);
    }
    return contentType.includes(type);
  });
}

// Fetch interception
function interceptFetch() {


  // Use Object.defineProperty to avoid prototype chain issues
  const interceptedFetch = async function(input, init = {}) {
    const url = typeof input === 'string' ? input : input.url;
    const method = init.method || 'GET';


    // Check if this request should be monitored
    if (!responseBodyCaptureEnabled || !monitorConfig ||
        !urlMatchesPatterns(url, monitorConfig.url_patterns)) {
      // Request not monitored, use original fetch
      return originalFetch.call(this, input, init);
    }


    const requestId = generateRequestId(url, method);
    const startTime = Date.now();

    try {
      // Call original fetch
      const response = await originalFetch.call(this, input, init);

      // Clone response to read body without consuming it
      const responseClone = response.clone();
      const endTime = Date.now();

      // Capture response body if enabled
      if (monitorConfig.options?.capture_response_bodies) {
        try {
          const contentType = response.headers.get('content-type') || '';
          const contentLength = parseInt(response.headers.get('content-length') || '0', 10);

          // Check if we should capture this content type
          if (shouldCaptureContentType(contentType, monitorConfig.options?.content_types_to_capture)) {
            const maxSize = monitorConfig.options?.max_body_size || 50000;

            // Read response body
            let responseBody = '';
            let truncated = false;

            if (contentType.includes('application/json') ||
                contentType.includes('text/') ||
                contentType.includes('application/xml')) {

              responseBody = await responseClone.text();

              // Check size limit
              if (responseBody.length > maxSize) {
                responseBody = responseBody.substring(0, maxSize);
                truncated = true;
              }
            }

            // Store captured response data
            const responseData = {
              request_id: requestId,
              url: url,
              method: method,
              status_code: response.status,
              status_text: response.statusText,
              content_type: contentType,
              content_length: contentLength,
              response_body: responseBody,
              truncated: truncated,
              duration_ms: endTime - startTime,
              timestamp: new Date().toISOString(),
              start_time: startTime,
              end_time: endTime,
              headers: {}
            };

            // Capture response headers
            response.headers.forEach((value, key) => {
              responseData.headers[key] = value;
            });

            capturedResponses.set(requestId, responseData);

            // Notify background script about captured response
            browser.runtime.sendMessage({
              type: 'response_body_captured',
              data: responseData
            }).catch(err => {
              console.log('Failed to notify background script:', err);
            });

            console.log(`📥 Captured response body for ${method} ${url} (${responseBody.length} chars)`);
          }
        } catch (error) {
          console.error('Error capturing response body:', error);
        }
      }

      return response;

    } catch (error) {
      // Handle fetch errors
      const endTime = Date.now();

      const errorData = {
        request_id: requestId,
        url: url,
        method: method,
        error: error.message,
        duration_ms: endTime - startTime,
        timestamp: new Date().toISOString()
      };

      // Notify about failed request
      browser.runtime.sendMessage({
        type: 'response_body_error',
        data: errorData
      }).catch(err => {
        console.log('Failed to notify about error:', err);
      });

      throw error;
    }
  };

  // Try to override window.fetch (with fallback)
  try {
    // Direct assignment first, then Object.defineProperty if needed
    window.fetch = interceptedFetch;

    // Check if it worked, fallback to Object.defineProperty if needed
    if (window.fetch.toString().includes('[native code]')) {
      Object.defineProperty(window, 'fetch', {
        value: interceptedFetch,
        writable: true,
        configurable: true
      });
    }
  } catch (error) {
    console.error('Failed to override window.fetch:', error.message);
  }
}

// XMLHttpRequest interception
function interceptXMLHttpRequest() {

  const interceptedXMLHttpRequest = function() {
    const xhr = new originalXMLHttpRequest();
    let requestUrl = '';
    let requestMethod = 'GET';
    let requestId = '';
    let startTime = 0;

    // Override open to capture request details
    const originalOpen = xhr.open;
    xhr.open = function(method, url, async, user, password) {
      requestUrl = url;
      requestMethod = method;
      requestId = generateRequestId(url, method);
      startTime = Date.now();

      return originalOpen.call(this, method, url, async, user, password);
    };

    // Override send to capture response
    const originalSend = xhr.send;
    xhr.send = function(data) {
      // Check if this request should be monitored
      if (responseBodyCaptureEnabled && monitorConfig &&
          urlMatchesPatterns(requestUrl, monitorConfig.url_patterns)) {

        xhr.addEventListener('load', function() {
          if (monitorConfig.options?.capture_response_bodies) {
            try {
              const endTime = Date.now();
              const contentType = xhr.getResponseHeader('content-type') || '';

              if (shouldCaptureContentType(contentType, monitorConfig.options?.content_types_to_capture)) {
                const maxSize = monitorConfig.options?.max_body_size || 50000;
                let responseBody = xhr.responseText || '';
                let truncated = false;

                if (responseBody.length > maxSize) {
                  responseBody = responseBody.substring(0, maxSize);
                  truncated = true;
                }

                const responseData = {
                  request_id: requestId,
                  url: requestUrl,
                  method: requestMethod,
                  status_code: xhr.status,
                  status_text: xhr.statusText,
                  content_type: contentType,
                  content_length: responseBody.length,
                  response_body: responseBody,
                  truncated: truncated,
                  duration_ms: endTime - startTime,
                  timestamp: new Date().toISOString(),
                  start_time: startTime,
                  end_time: endTime,
                  headers: {}
                };

                // Capture response headers (getAllResponseHeaders returns a string)
                const headerString = xhr.getAllResponseHeaders();
                if (headerString) {
                  headerString.split('\r\n').forEach(line => {
                    const [key, value] = line.split(': ');
                    if (key && value) {
                      responseData.headers[key.toLowerCase()] = value;
                    }
                  });
                }

                capturedResponses.set(requestId, responseData);

                browser.runtime.sendMessage({
                  type: 'response_body_captured',
                  data: responseData
                }).catch(err => {
                  console.log('Failed to notify background script:', err);
                });

                console.log(`📥 Captured XHR response body for ${requestMethod} ${requestUrl} (${responseBody.length} chars)`);
              }
            } catch (error) {
              console.error('Error capturing XHR response body:', error);
            }
          }
        });

        xhr.addEventListener('error', function() {
          const endTime = Date.now();

          const errorData = {
            request_id: requestId,
            url: requestUrl,
            method: requestMethod,
            error: 'Network error',
            duration_ms: endTime - startTime,
            timestamp: new Date().toISOString()
          };

          browser.runtime.sendMessage({
            type: 'response_body_error',
            data: errorData
          }).catch(err => {
            console.log('Failed to notify about XHR error:', err);
          });
        });
      }

      return originalSend.call(this, data);
    };

    return xhr;
  };

  // Override window.XMLHttpRequest
  try {
    Object.defineProperty(window, 'XMLHttpRequest', {
      value: interceptedXMLHttpRequest,
      writable: true,
      configurable: true
    });

    // Copy over static properties from original XMLHttpRequest
    for (const prop in originalXMLHttpRequest) {
      if (originalXMLHttpRequest.hasOwnProperty(prop)) {
        interceptedXMLHttpRequest[prop] = originalXMLHttpRequest[prop];
      }
    }
  } catch (error) {
    console.error('Failed to override window.XMLHttpRequest:', error.message);
  }
}

// Restore original implementations
function restoreOriginalImplementations() {
  window.fetch = originalFetch;
  window.XMLHttpRequest = originalXMLHttpRequest;
  responseBodyCaptureEnabled = false;
  monitorConfig = null;
  capturedResponses.clear();
  console.log('🔄 Restored original fetch and XMLHttpRequest implementations');
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

      case 'enable_response_capture':
        monitorConfig = data.monitor_config;
        responseBodyCaptureEnabled = true;

        // Set up interception
        interceptFetch();
        interceptXMLHttpRequest();

        console.log('🌐 Response body capture enabled for patterns:', monitorConfig.url_patterns);
        sendResponse({ success: true, message: 'Response body capture enabled' });
        break;

      case 'disable_response_capture':
        restoreOriginalImplementations();
        sendResponse({ success: true, message: 'Response body capture disabled' });
        break;

      case 'get_captured_response':
        const requestId = data.request_id;
        const capturedData = capturedResponses.get(requestId);
        if (capturedData) {
          sendResponse({ success: true, data: capturedData });
        } else {
          sendResponse({ success: false, error: 'Response data not found' });
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