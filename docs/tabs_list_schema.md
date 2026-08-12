# `tabs_list()` Function Format and Schema Documentation

## Overview
The `tabs_list()` MCP tool returns a formatted string listing open browser tabs with their properties and status indicators. By default it lists the tabs of every window; passing `window_id` restricts it to one.

## Function Signature
```python
async def tabs_list(window_id: Optional[Union[int, str]] = None) -> str
```

`window_id` accepts an int or a string, for MCP clients that send numbers as text. A value that is not a number returns `"Error: Invalid window_id ..."` without a request being sent.

## Data Flow Schema

### 1. WebSocket Request Format
```json
{
  "id": "uuid-string",
  "type": "request", 
  "action": "tabs.list",
  "data": {
    "windowId": 1
  },
  "timestamp": "ISO-8601-timestamp"
}
```

`windowId` is omitted entirely when no window was named — an absent key is what tells the extension to query every window.

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
  index: number;      // Position within its window, counting from 0
}
```

### 3. MCP Tool Output Format

The `tabs_list()` function returns a formatted string with the following structure:

#### Success Response Format
```
Open tabs ({count} found):
- ID {tab_id}: {title} - {url}{status_indicators} [window {window_id}, index {index}]
- ID {tab_id}: {title} - {url}{status_indicators} [window {window_id}, index {index}]
...
```

**Format Explanation:**
- **Header Line**: `"Open tabs ({count} found):"` where `{count}` is the total number of tabs. When a window was named, the header reads `"Open tabs in window {window_id} ({count} found):"`
- **Tab Lines**: Each tab is formatted as: `"- ID {tab_id}: {title} - {url}{status_indicators} [window {window_id}, index {index}]"`
  - `{tab_id}`: Numeric browser tab identifier
  - `{title}`: Page title (or "No title" if missing)
  - `{url}`: Full URL (or "No URL" if missing)
  - `{status_indicators}`: Optional status flags (see below)
  - `{window_id}`: The window holding the tab — pass it to `tabs_move` to move tabs there
  - `{index}`: The tab's position in that window, counting from 0 — pass it to `tabs_move` to reorder

The location comes last, after the status indicators, so that the tab ID stays adjacent to its colon: callers pick IDs out of this listing with an `ID (\d+):` pattern, and the test suite does too.

#### Status Indicators
- `(active)` - Appended when `tab.active === true`
- `(pinned)` - Appended when `tab.pinned === true`
- Both indicators can appear together: `(active)(pinned)`

#### Error Response Formats
- `"Error getting tabs: {error_message}"` - WebSocket communication error
- `"No tabs found. Extension response: {response_data}"` - No tabs returned
- `"Unable to retrieve tabs"` - Unexpected response format

## Example Outputs

### Example 1: Mixed Tab Types, Across Two Windows
```
Open tabs (4 found):
- ID 1: New Tab - chrome://browser/content/blanktab.html [window 1, index 0]
- ID 2: Example Domain - https://example.com/ (active) [window 1, index 1]
- ID 3: GitHub - https://github.com/ (pinned) [window 2, index 0]
- ID 4: Google - https://google.com (active)(pinned) [window 2, index 1]
```

### Example 1b: One Window Only
```python
await client.call_tool("tabs_list", {"window_id": 2})
```
```
Open tabs in window 2 (2 found):
- ID 3: GitHub - https://github.com/ (pinned) [window 2, index 0]
- ID 4: Google - https://google.com (active)(pinned) [window 2, index 1]
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
| `index` | number | Position within its window, counting from 0 | `2` |

## Status Indicators Logic
```python
active = " (active)" if tab.get("active") else ""
pinned = " (pinned)" if tab.get("pinned") else ""
location = f" [window {tab.get('windowId')}, index {tab.get('index')}]"
result += f"- ID {tab.get('id')}: {tab.get('title', 'No title')} - {tab.get('url', 'No URL')}{active}{pinned}{location}\n"
```

## Browser API Integration
The function queries the browser using:
```javascript
const tabQuery = data.windowId ? { windowId: data.windowId } : {};
const tabs = await browser.tabs.query(tabQuery);
```

An empty query object matches every tab in every window. The filter has to be left out rather than passed as a falsy value, because `{windowId: undefined}` matches nothing.

Until 2026-08-12 this read `currentWindow: data.currentWindow || true`, where the `|| true` made the filter unconditional: the listing was always limited to the current window, whatever the request asked for, and no caller could reach a tab in another window.

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
- `tabs_move()` - Reorder tabs, or move them into another window, using the window and index this listing reports
- `list_windows()` - List windows with tab counts