# WebSocket Message Protocol

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
    "code": "document.title"
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
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

### 5. Bookmark Management

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
        "dateAdded": "2025-09-01T10:00:00.000Z",
        "isFolder": false
      },
      {
        "id": "bm_002", 
        "parentId": "1",
        "title": "Development",
        "dateAdded": "2025-09-01T09:00:00.000Z",
        "isFolder": true,
        "children": []
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
- `BOOKMARK_NOT_FOUND` - Specified bookmark ID doesn't exist
- `INVALID_URL` - Provided URL is malformed
- `SCRIPT_EXECUTION_FAILED` - JavaScript execution failed
- `WEBSOCKET_ERROR` - Connection or communication error
- `INVALID_REQUEST` - Malformed request message
- `UNKNOWN_ACTION` - Unsupported action requested