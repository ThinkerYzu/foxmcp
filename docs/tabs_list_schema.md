# `tabs_list()` Function Format and Schema Documentation

## Overview
The `tabs_list()` MCP tool returns a formatted string listing all open browser tabs with their properties and status indicators.

## Function Signature
```python
async def tabs_list() -> str
```

## Data Flow Schema

### 1. WebSocket Request Format
```json
{
  "id": "uuid-string",
  "type": "request", 
  "action": "tabs.list",
  "data": {},
  "timestamp": "ISO-8601-timestamp"
}
```

### 2. Extension Response Schema
```typescript
interface TabsListResponse {
  tabs: TabInfo[];
  debug: {
    totalFound: number;
    tabUrls: string[];
  };
}

interface TabInfo {
  url: string;        // Full URL of the tab
  id: number;         // Unique tab ID
  title: string;      // Page title
  active: boolean;    // Whether tab is currently active
  windowId: number;   // ID of the window containing this tab
  pinned: boolean;    // Whether tab is pinned
}
```

### 3. MCP Tool Output Format

The `tabs_list()` function returns a formatted string with the following structure:

#### Success Response Format
```
Open tabs ({count} found):
- ID {tab_id}: {title} - {url}{status_indicators}
- ID {tab_id}: {title} - {url}{status_indicators}
...
```

**Format Explanation:**
- **Header Line**: `"Open tabs ({count} found):"` where `{count}` is the total number of tabs
- **Tab Lines**: Each tab is formatted as: `"- ID {tab_id}: {title} - {url}{status_indicators}"`
  - `{tab_id}`: Numeric browser tab identifier
  - `{title}`: Page title (or "No title" if missing)
  - `{url}`: Full URL (or "No URL" if missing)
  - `{status_indicators}`: Optional status flags (see below)

#### Status Indicators
- `(active)` - Appended when `tab.active === true`
- `(pinned)` - Appended when `tab.pinned === true`
- Both indicators can appear together: `(active)(pinned)`

#### Error Response Formats
- `"Error getting tabs: {error_message}"` - WebSocket communication error
- `"No tabs found. Extension response: {response_data}"` - No tabs returned
- `"Unable to retrieve tabs"` - Unexpected response format

## Example Outputs

### Example 1: Mixed Tab Types
```
Open tabs (4 found):
- ID 1: New Tab - chrome://browser/content/blanktab.html
- ID 2: Example Domain - https://example.com/ (active)
- ID 3: GitHub - https://github.com/ (pinned)
- ID 4: Google - https://google.com (active)(pinned)
```

### Example 2: No Tabs
```
No tabs found. Extension response: {"tabs": [], "debug": {"totalFound": 0, "tabUrls": []}}
```

### Example 3: Error Case
```
Error getting tabs: WebSocket connection lost
```

## Field Descriptions

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `id` | number | Unique browser tab identifier | `123` |
| `title` | string | Page title from `<title>` tag | `"GitHub - Where software is built"` |
| `url` | string | Full URL including protocol | `"https://github.com"` |
| `active` | boolean | Current active tab in window | `true` |
| `windowId` | number | ID of containing browser window | `1` |
| `pinned` | boolean | Whether tab is pinned to tab bar | `true` |

## Status Indicators Logic
```python
active = " (active)" if tab.get("active") else ""
pinned = " (pinned)" if tab.get("pinned") else ""
result += f"- ID {tab.get('id')}: {tab.get('title', 'No title')} - {tab.get('url', 'No URL')}{active}{pinned}\n"
```

## Browser API Integration
The function queries the browser using:
```javascript
const tabs = await browser.tabs.query({
  currentWindow: data.currentWindow || true
});
```

## Use Cases
- **Tab Management**: List all tabs before performing operations
- **Session Analysis**: Understand current browser state
- **Tab Filtering**: Identify pinned or active tabs
- **Cross-Window Operations**: See tabs across all windows
- **Debugging**: Inspect tab properties and status

## Implementation Notes
- Uses WebSocket communication between MCP server and browser extension
- Fallback values: `'No title'` for missing titles, `'No URL'` for missing URLs
- Includes debug information in extension response for troubleshooting
- Returns immediately available tab data (no additional page loading)
- Compatible with Firefox WebExtensions API via `browser.tabs.query()`

## Related Functions
- `tabs_create()` - Create new tabs (can set pinned status)
- `tabs_close()` - Close specific tabs by ID
- `tabs_switch()` - Switch to specific tab by ID
- `windows_list()` - List windows with tab counts