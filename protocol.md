# WebSocket Message Protocol

## Connection Constraints

**IMPORTANT: Only one extension connection is allowed at a time.**

- The FoxMCP server accepts only one active WebSocket connection from a browser extension
- If a new connection arrives, the existing connection is automatically closed
- The extension disconnects any existing connection before creating a new one
- This prevents connection races, resource conflicts, and multiple extension instances

## Message Structure

All messages follow this JSON structure:
```json
{
  "id": "unique-request-id",
  "type": "request|response|error", 
  "action": "function_name",
  "data": {...},
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

## Request/Response Examples

### 1. History Management

#### Query History
**Request:**
```json
{
  "id": "req_001",
  "type": "request",
  "action": "history.query",
  "data": {
    "query": "github",
    "maxResults": 50,
    "startTime": "2025-09-01T00:00:00.000Z",
    "endTime": "2025-09-03T23:59:59.000Z"
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

**Response:**
```json
{
  "id": "req_001",
  "type": "response",
  "action": "history.query",
  "data": {
    "items": [
      {
        "id": "hist_123",
        "url": "https://github.com/user/repo",
        "title": "GitHub Repository",
        "visitTime": "2025-09-02T14:30:00.000Z",
        "visitCount": 5
      }
    ],
    "totalCount": 1
  },
  "timestamp": "2025-09-03T12:00:01.000Z"
}
```

#### Get Recent History
**Request:**
```json
{
  "id": "req_002", 
  "type": "request",
  "action": "history.get_recent",
  "data": {
    "count": 10
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

#### Delete History Item
**Request:**
```json
{
  "id": "req_003",
  "type": "request", 
  "action": "history.delete_item",
  "data": {
    "url": "https://example.com/page"
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

### 2. Tab Management

#### List All Tabs
**Request:**
```json
{
  "id": "req_004",
  "type": "request",
  "action": "tabs.list",
  "data": {},
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

**Response:**
```json
{
  "id": "req_004",
  "type": "response", 
  "action": "tabs.list",
  "data": {
    "tabs": [
      {
        "id": 123,
        "windowId": 1,
        "url": "https://example.com",
        "title": "Example Page",
        "active": true,
        "index": 0,
        "pinned": false,
        "favIconUrl": "https://example.com/favicon.ico"
      },
      {
        "id": 124,
        "windowId": 1, 
        "url": "https://github.com",
        "title": "GitHub",
        "active": false,
        "index": 1,
        "pinned": false,
        "favIconUrl": "https://github.com/favicon.ico"
      }
    ]
  },
  "timestamp": "2025-09-03T12:00:01.000Z"
}
```

#### Create New Tab
**Request:**
```json
{
  "id": "req_005",
  "type": "request",
  "action": "tabs.create", 
  "data": {
    "url": "https://example.com",
    "active": true,
    "pinned": false,
    "windowId": 1
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

**Response:**
```json
{
  "id": "req_005",
  "type": "response",
  "action": "tabs.create",
  "data": {
    "tab": {
      "id": 125,
      "windowId": 1,
      "url": "https://example.com", 
      "title": "Loading...",
      "active": true,
      "index": 2,
      "pinned": false
    }
  },
  "timestamp": "2025-09-03T12:00:01.000Z"
}
```

#### Close Tab
**Request:**
```json
{
  "id": "req_006",
  "type": "request",
  "action": "tabs.close",
  "data": {
    "tabId": 124
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

#### Switch to Tab
**Request:**
```json
{
  "id": "req_007",
  "type": "request",
  "action": "tabs.switch",
  "data": {
    "tabId": 123
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

#### Capture Screenshot of Tab
**Request:**
```json
{
  "id": "req_007b",
  "type": "request",
  "action": "tabs.captureVisibleTab",
  "data": {
    "windowId": 1,
    "format": "png",
    "quality": 90
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

**Response:**
```json
{
  "id": "req_007b",
  "type": "response",
  "action": "tabs.captureVisibleTab",
  "data": {
    "dataUrl": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
    "format": "png",
    "quality": 90,
    "windowId": 1
  },
  "timestamp": "2025-09-03T12:00:01.000Z"
}
```

### 3. Tab Content

#### Get Page Content
**Request:**
```json
{
  "id": "req_008",
  "type": "request", 
  "action": "content.get_text",
  "data": {
    "tabId": 123
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

**Response:**
```json
{
  "id": "req_008", 
  "type": "response",
  "action": "content.get_text",
  "data": {
    "text": "This is the page content...",
    "url": "https://example.com",
    "title": "Example Page"
  },
  "timestamp": "2025-09-03T12:00:01.000Z"
}
```

#### Get HTML Content
**Request:**
```json
{
  "id": "req_009",
  "type": "request",
  "action": "content.get_html", 
  "data": {
    "tabId": 123
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

#### Execute Script
**Request:**
```json
{
  "id": "req_010",
  "type": "request",
  "action": "content.execute_script",
  "data": {
    "tabId": 123,
    "script": "document.title"
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

**Response:**
```json
{
  "id": "req_010", 
  "type": "response",
  "action": "content.execute_script",
  "data": {
    "result": "My Page Title",
    "url": "https://example.com"
  },
  "timestamp": "2025-09-03T12:00:01.000Z"
}
```

#### Execute Predefined Script
**Request:**
```json
{
  "id": "req_010b",
  "type": "request",
  "action": "content.execute_predefined",
  "data": {
    "tabId": 123,
    "scriptName": "get_page_info.sh",
    "scriptArgs": ["title"]
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

**Response:**
```json
{
  "id": "req_010b",
  "type": "response", 
  "action": "content.execute_predefined",
  "data": {
    "result": "My Page Title",
    "url": "https://example.com",
    "scriptName": "get_page_info.sh",
    "scriptOutput": "document.title"
  },
  "timestamp": "2025-09-03T12:00:01.000Z"
}
```

**Security Validation Response:**
```json
{
  "id": "req_010c",
  "type": "error",
  "action": "content.execute_predefined",
  "data": {
    "code": "INVALID_SCRIPT_NAME",
    "message": "Invalid script name '../../../etc/passwd'. Script names cannot contain path separators or '..' sequences"
  },
  "timestamp": "2025-09-03T12:00:01.000Z"
}
```

### 4. Navigation

#### Navigate Back
**Request:**
```json
{
  "id": "req_011",
  "type": "request",
  "action": "navigation.back",
  "data": {
    "tabId": 123
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

#### Navigate Forward
**Request:**
```json
{
  "id": "req_012", 
  "type": "request",
  "action": "navigation.forward",
  "data": {
    "tabId": 123
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

#### Go to URL
**Request:**
```json
{
  "id": "req_013",
  "type": "request",
  "action": "navigation.go_to_url",
  "data": {
    "tabId": 123,
    "url": "https://newsite.com"
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

#### Reload Page
**Request:**
```json
{
  "id": "req_014",
  "type": "request", 
  "action": "navigation.reload",
  "data": {
    "tabId": 123,
    "bypassCache": false
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

### 5. Window Management

#### List All Windows
**Request:**
```json
{
  "id": "req_020",
  "type": "request",
  "action": "windows.list",
  "data": {},
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

**Response:**
```json
{
  "id": "req_020",
  "type": "response",
  "action": "windows.list",
  "data": {
    "windows": [
      {
        "id": 1,
        "type": "normal",
        "state": "normal",
        "focused": true,
        "top": 100,
        "left": 150,
        "width": 1024,
        "height": 768,
        "incognito": false,
        "sessionId": "session_1",
        "tabs": [
          {
            "id": 123,
            "url": "https://example.com",
            "title": "Example Page",
            "active": true
          }
        ]
      }
    ]
  },
  "timestamp": "2025-09-03T12:00:01.000Z"
}
```

#### Get Window Information
**Request:**
```json
{
  "id": "req_021",
  "type": "request",
  "action": "windows.get",
  "data": {
    "windowId": 1,
    "populate": true
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

**Response:**
```json
{
  "id": "req_021",
  "type": "response",
  "action": "windows.get",
  "data": {
    "window": {
      "id": 1,
      "type": "normal",
      "state": "normal",
      "focused": true,
      "top": 100,
      "left": 150,
      "width": 1024,
      "height": 768,
      "incognito": false,
      "sessionId": "session_1",
      "tabs": [
        {
          "id": 123,
          "url": "https://example.com",
          "title": "Example Page",
          "active": true,
          "index": 0
        }
      ]
    }
  },
  "timestamp": "2025-09-03T12:00:01.000Z"
}
```

#### Get Current Window
**Request:**
```json
{
  "id": "req_022",
  "type": "request",
  "action": "windows.get_current",
  "data": {
    "populate": false
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

#### Create New Window
**Request:**
```json
{
  "id": "req_023",
  "type": "request",
  "action": "windows.create",
  "data": {
    "url": "https://example.com",
    "type": "normal",
    "state": "normal",
    "focused": true,
    "width": 800,
    "height": 600,
    "top": 200,
    "left": 300,
    "incognito": false
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

**Response:**
```json
{
  "id": "req_023",
  "type": "response",
  "action": "windows.create",
  "data": {
    "window": {
      "id": 2,
      "type": "normal",
      "state": "normal",
      "focused": true,
      "top": 200,
      "left": 300,
      "width": 800,
      "height": 600,
      "incognito": false,
      "tabs": [
        {
          "id": 124,
          "url": "https://example.com",
          "title": "Loading...",
          "active": true,
          "index": 0
        }
      ]
    }
  },
  "timestamp": "2025-09-03T12:00:01.000Z"
}
```

#### Close Window
**Request:**
```json
{
  "id": "req_024",
  "type": "request",
  "action": "windows.close",
  "data": {
    "windowId": 2
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

**Response:**
```json
{
  "id": "req_024",
  "type": "response",
  "action": "windows.close",
  "data": {
    "success": true,
    "windowId": 2
  },
  "timestamp": "2025-09-03T12:00:01.000Z"
}
```

#### Focus Window
**Request:**
```json
{
  "id": "req_025",
  "type": "request",
  "action": "windows.focus",
  "data": {
    "windowId": 1
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

### 6. Bookmark Management

#### List Bookmarks
**Request:**
```json
{
  "id": "req_015",
  "type": "request",
  "action": "bookmarks.list",
  "data": {
    "folderId": "1"
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

**Response:**
```json
{
  "id": "req_015",
  "type": "response",
  "action": "bookmarks.list", 
  "data": {
    "bookmarks": [
      {
        "id": "bm_001",
        "parentId": "1",
        "title": "GitHub",
        "url": "https://github.com",
        "isFolder": false
      },
      {
        "id": "bm_002", 
        "parentId": "1",
        "title": "Development",
        "isFolder": true
      }
    ]
  },
  "timestamp": "2025-09-03T12:00:01.000Z"
}
```

#### Search Bookmarks
**Request:**
```json
{
  "id": "req_016",
  "type": "request",
  "action": "bookmarks.search",
  "data": {
    "query": "github"
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

#### Create Bookmark
**Request:**
```json
{
  "id": "req_017",
  "type": "request",
  "action": "bookmarks.create", 
  "data": {
    "title": "New Site",
    "url": "https://newsite.com",
    "parentId": "1"
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

**Response:**
```json
{
  "id": "req_017",
  "type": "response",
  "action": "bookmarks.create",
  "data": {
    "bookmark": {
      "id": "bm_003",
      "parentId": "1", 
      "title": "New Site",
      "url": "https://newsite.com",
      "dateAdded": "2025-09-03T12:00:00.000Z",
      "isFolder": false
    }
  },
  "timestamp": "2025-09-03T12:00:01.000Z"
}
```

#### Delete Bookmark
**Request:**
```json
{
  "id": "req_018",
  "type": "request",
  "action": "bookmarks.delete",
  "data": {
    "bookmarkId": "bm_003"
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

## Error Messages

**Error Response:**
```json
{
  "id": "req_001",
  "type": "error", 
  "action": "tabs.close",
  "data": {
    "code": "TAB_NOT_FOUND",
    "message": "Tab with ID 999 not found",
    "details": {
      "tabId": 999
    }
  },
  "timestamp": "2025-09-03T12:00:01.000Z"
}
```

## Error Codes

- `PERMISSION_DENIED` - Extension lacks required permissions
- `TAB_NOT_FOUND` - Specified tab ID doesn't exist
- `WINDOW_NOT_FOUND` - Specified window ID doesn't exist
- `BOOKMARK_NOT_FOUND` - Specified bookmark ID doesn't exist
- `INVALID_URL` - Provided URL is malformed
- `INVALID_WINDOW_STATE` - Invalid window state specified
- `INVALID_WINDOW_TYPE` - Invalid window type specified
- `WINDOW_CREATION_FAILED` - Failed to create new window
- `SCRIPT_EXECUTION_FAILED` - JavaScript execution failed
- `WEBSOCKET_ERROR` - Connection or communication error
- `INVALID_REQUEST` - Malformed request message
- `UNKNOWN_ACTION` - Unsupported action requested
- `INVALID_SCRIPT_NAME` - Script name contains invalid characters or path traversal attempts
- `SCRIPT_NOT_FOUND` - External script file not found in configured directory
- `SCRIPT_NOT_EXECUTABLE` - External script file lacks execute permissions
- `INVALID_JSON` - Script arguments contain malformed JSON
- `INVALID_SCRIPT_ARGS` - Script arguments must be JSON array of strings or empty string
- `CAPTURE_ERROR` - Failed to capture screenshot of the visible tab

## Test Helper Messages

The extension provides test helper messages for automated testing and validation of UI state synchronization.

### Get Popup Display State

**Request:**
```json
{
  "id": "test_001",
  "type": "request", 
  "action": "test.get_popup_state",
  "data": {},
  "timestamp": "2025-09-04T12:00:00.000Z"
}
```

**Response:**
```json
{
  "id": "test_001",
  "type": "response",
  "action": "test.get_popup_state", 
  "data": {
    "serverUrl": "ws://localhost:7777",
    "retryInterval": 1000,
    "maxRetries": 5,
    "pingTimeout": 2000,
    "hasTestOverrides": true,
    "effectiveHostname": "localhost",
    "effectivePort": 7777,
    "testIndicatorShown": true,
    "storageValues": {
      "hostname": "localhost",
      "port": 8765,
      "testPort": 7777,
      "testHostname": "localhost"
    }
  },
  "timestamp": "2025-09-04T12:00:00.500Z"
}
```

### Get Options Page State

**Request:**
```json
{
  "id": "test_002", 
  "type": "request",
  "action": "test.get_options_state",
  "data": {},
  "timestamp": "2025-09-04T12:00:01.000Z"
}
```

**Response:**
```json
{
  "id": "test_002",
  "type": "response",
  "action": "test.get_options_state",
  "data": {
    "displayHostname": "localhost",
    "displayPort": 7777,
    "retryInterval": 1000,
    "maxRetries": 5,
    "pingTimeout": 2000,
    "webSocketUrl": "ws://localhost:7777",
    "hasTestOverrides": true,
    "testOverrideWarningShown": true,
    "storageValues": {
      "hostname": "localhost", 
      "port": 8765,
      "testPort": 7777,
      "testHostname": "localhost"
    }
  },
  "timestamp": "2025-09-04T12:00:01.500Z"
}
```

### Get Raw Storage Values

**Request:**
```json
{
  "id": "test_003",
  "type": "request",
  "action": "test.get_storage_values",
  "data": {},
  "timestamp": "2025-09-04T12:00:02.000Z"
}
```

**Response:**
```json
{
  "id": "test_003",
  "type": "response", 
  "action": "test.get_storage_values",
  "data": {
    "hostname": "localhost",
    "port": 8765,
    "retryInterval": 1000,
    "maxRetries": 5,
    "pingTimeout": 2000,
    "testPort": 7777,
    "testHostname": "localhost"
  },
  "timestamp": "2025-09-04T12:00:02.500Z"
}
```

### Validate UI-Storage Sync

**Request:**
```json
{
  "id": "test_004",
  "type": "request",
  "action": "test.validate_ui_sync",
  "data": {
    "expectedValues": {
      "hostname": "example.com",
      "port": 9000,
      "testPort": 7777,
      "testHostname": "test.local"
    }
  },
  "timestamp": "2025-09-04T12:00:03.000Z"
}
```

**Response:**
```json
{
  "id": "test_004", 
  "type": "response",
  "action": "test.validate_ui_sync",
  "data": {
    "popupSyncValid": true,
    "optionsSyncValid": true,
    "storageMatches": true,
    "effectiveValues": {
      "hostname": "test.local",
      "port": 7777
    },
    "issues": []
  },
  "timestamp": "2025-09-04T12:00:03.500Z"
}
```

### Trigger UI State Refresh

**Request:**
```json
{
  "id": "test_005",
  "type": "request",
  "action": "test.refresh_ui_state",
  "data": {},
  "timestamp": "2025-09-04T12:00:04.000Z"
}
```

**Response:**
```json
{
  "id": "test_005",
  "type": "response",
  "action": "test.refresh_ui_state", 
  "data": {
    "refreshed": true,
    "popupStateUpdated": true,
    "optionsStateUpdated": true
  },
  "timestamp": "2025-09-04T12:00:04.500Z"
}
```

### Visit URL for History Testing

**Request:**
```json
{
  "id": "test_006",
  "type": "request",
  "action": "test.visit_url",
  "data": {
    "url": "https://httpbin.org/json",
    "waitTime": 2000
  },
  "timestamp": "2025-09-05T12:00:00.000Z"
}
```

**Response:**
```json
{
  "id": "test_006",
  "type": "response",
  "action": "test.visit_url",
  "data": {
    "success": true,
    "url": "https://httpbin.org/json",
    "tabId": 123,
    "visitTime": "2025-09-05T12:00:01.000Z",
    "message": "Successfully visited https://httpbin.org/json"
  },
  "timestamp": "2025-09-05T12:00:03.000Z"
}
```

### Visit Multiple URLs for History Testing

**Request:**
```json
{
  "id": "test_007",
  "type": "request",
  "action": "test.visit_multiple_urls",
  "data": {
    "urls": [
      "https://httpbin.org/status/200",
      "https://httpbin.org/user-agent",
      "https://httpbin.org/headers"
    ],
    "waitTime": 1500,
    "delayBetween": 500
  },
  "timestamp": "2025-09-05T12:00:00.000Z"
}
```

**Response:**
```json
{
  "id": "test_007",
  "type": "response",
  "action": "test.visit_multiple_urls",
  "data": {
    "success": true,
    "totalUrls": 3,
    "successfulVisits": 3,
    "failedVisits": 0,
    "results": [
      {
        "url": "https://httpbin.org/status/200",
        "success": true,
        "tabId": 124,
        "visitTime": "2025-09-05T12:00:01.500Z"
      },
      {
        "url": "https://httpbin.org/user-agent",
        "success": true,
        "tabId": 125,
        "visitTime": "2025-09-05T12:00:03.000Z"
      },
      {
        "url": "https://httpbin.org/headers",
        "success": true,
        "tabId": 126,
        "visitTime": "2025-09-05T12:00:04.500Z"
      }
    ],
    "message": "Visited 3/3 URLs successfully"
  },
  "timestamp": "2025-09-05T12:00:06.000Z"
}
```

### Clear Test History

**Request:**
```json
{
  "id": "test_008",
  "type": "request",
  "action": "test.clear_test_history",
  "data": {
    "urls": [
      "https://httpbin.org/status/200",
      "https://httpbin.org/user-agent"
    ]
  },
  "timestamp": "2025-09-05T12:00:00.000Z"
}
```

**Response:**
```json
{
  "id": "test_008",
  "type": "response",
  "action": "test.clear_test_history",
  "data": {
    "success": true,
    "action": "cleared_specific_urls",
    "totalUrls": 2,
    "successfulClears": 2,
    "failedClears": 0,
    "results": [
      {
        "url": "https://httpbin.org/status/200",
        "success": true
      },
      {
        "url": "https://httpbin.org/user-agent",
        "success": true
      }
    ],
    "message": "Cleared 2/2 URLs from history"
  },
  "timestamp": "2025-09-05T12:00:01.000Z"
}
```

## Test Helper Usage

Test helpers enable automated validation of:

- **Storage-UI Synchronization**: Verify popup and options pages display current storage values
- **Test Override Priority**: Confirm test configurations take precedence over regular settings
- **Configuration Persistence**: Validate that UI changes preserve test overrides
- **State Consistency**: Ensure all UI components reflect the same effective configuration
- **Browser History Testing**: Create and verify actual browser history content
- **History Content Validation**: Test history queries with real visited URLs
- **History Cleanup**: Clean up test history entries for isolated testing

Example test workflows:

**UI Synchronization Testing:**
1. Set test configuration via storage
2. Use `test.get_popup_state` to verify popup displays test values
3. Use `test.validate_ui_sync` to confirm UI-storage alignment
4. Modify configuration and verify persistence

**History Content Testing:**
1. Use `test.visit_url` or `test.visit_multiple_urls` to create real browser history
2. Use `history.query` or `history.recent` to verify the visited URLs appear
3. Validate history item structure and timestamps
4. Use `test.clear_test_history` to clean up test data