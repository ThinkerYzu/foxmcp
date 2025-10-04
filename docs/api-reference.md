# FoxMCP API Reference

Complete reference for all MCP tools and browser functions available through FoxMCP.

## Available MCP Tools

### Tab Management
- `tabs_list()` - List all open tabs
- `tabs_create(url, active=True, pinned=False, window_id=None)` - Create new tab (optionally in specific window)
- `tabs_close(tab_id)` - Close specific tab
- `tabs_switch(tab_id)` - Switch to specific tab
- `tabs_capture_screenshot(filename=None, window_id=None, format="png", quality=90)` - Capture screenshot of visible tab
  - If `filename` provided: saves screenshot to file and returns success message
  - If `filename` omitted: returns base64 encoded image data URL
  - Automatically adds file extension (.png/.jpeg) if not provided

### History Operations
- `history_query(query, max_results=50)` - Search browser history
- `history_get_recent(count=10)` - Get recent history items
- `history_delete_item(url)` - Delete specific history item

### Bookmark Management
- `bookmarks_list(folder_id=None)` - List bookmarks from all folders or a specific folder
  - Returns formatted text with folder (📁) and bookmark (🔖) entries
  - Each item includes unique ID and parent folder ID for navigation
  - When `folder_id` is provided, returns only direct children of that folder
- `bookmarks_search(query)` - Search bookmarks by title or URL
  - Returns formatted text with matching bookmark entries including ID and parent folder ID
- `bookmarks_create(title, url, parent_id=None)` - Create bookmark
- `bookmarks_create_folder(title, parent_id=None)` - Create bookmark folder
- `bookmarks_update(bookmark_id, title=None, url=None)` - Update bookmark or folder title/URL
- `bookmarks_delete(bookmark_id)` - Delete bookmark

### Navigation Control
- `navigation_back(tab_id)` - Navigate back in tab
- `navigation_forward(tab_id)` - Navigate forward in tab
- `navigation_reload(tab_id, bypass_cache=False)` - Reload tab
- `navigation_go_to_url(tab_id, url)` - Navigate to URL

### Content Access
- `content_get_text(tab_id, max_length=None)` - Extract page text content
  - `max_length`: Optional maximum length of text to return (default: unlimited)
- `content_get_html(tab_id)` - Get page HTML source
- `content_execute_script(tab_id, script)` - Execute JavaScript directly
- `content_execute_predefined(tab_id, script_name, script_args="")` - Execute predefined external scripts

### Web Request Monitoring
- `requests_start_monitoring(url_patterns, options=None, tab_id=None)` - Start monitoring web requests
  - `url_patterns`: List of URL patterns to monitor (e.g., `["https://api.example.com/*", "*/api/*"]`)
  - `options`: Optional configuration dict with capture settings
  - `tab_id`: Optional tab ID to monitor (if not provided, monitors all tabs)
  - Returns JSON with `monitor_id` and monitoring status
- `requests_stop_monitoring(monitor_id, drain_timeout=5)` - Stop monitoring with graceful drainage
  - `monitor_id`: ID of the monitoring session to stop
  - `drain_timeout`: Seconds to wait for in-flight requests
  - Returns JSON with stop status and statistics
- `requests_list_captured(monitor_id)` - List captured request summaries
  - Returns JSON with array of request summaries (metadata only, no full content)
- `requests_get_content(monitor_id, request_id, include_binary=False, save_request_body_to=None, save_response_body_to=None)` - Get full request/response content
  - `include_binary`: Whether to return binary content as base64 (default: False)
  - `save_request_body_to`: Optional file path to save request body
  - `save_response_body_to`: Optional file path to save response body
  - Returns JSON with full headers and content

### Window Management
- `list_windows(populate=True)` - List all browser windows with optional tab details
- `get_window(window_id, populate=True)` - Get specific window information
- `get_current_window(populate=True)` - Get current active window
- `get_last_focused_window(populate=True)` - Get most recently focused window
- `create_window(url=None, window_type="normal", state="normal", focused=True, width=None, height=None, top=None, left=None, incognito=False)` - Create new browser window
- `close_window(window_id)` - Close specific window
- `focus_window(window_id)` - Bring window to front and focus it
- `update_window(window_id, state=None, focused=None, width=None, height=None, top=None, left=None)` - Update window properties

### Debugging Tools
- `debug_websocket_status()` - Check browser extension connection status

## Usage Examples

### Basic Tab Operations
```python
# List all tabs
tabs = await client.call_tool("tabs_list")

# Create new tab
result = await client.call_tool("tabs_create", {"url": "https://example.com"})

# Take screenshot
screenshot = await client.call_tool("tabs_capture_screenshot", {"format": "png"})
```

### History and Bookmarks
```python
# Search history
history = await client.call_tool("history_query", {"query": "python", "max_results": 10})

# List bookmarks
bookmarks = await client.call_tool("bookmarks_list")

# Create bookmark
bookmark = await client.call_tool("bookmarks_create", {
    "title": "Example Site",
    "url": "https://example.com"
})

# Create bookmark folder
folder = await client.call_tool("bookmarks_create_folder", {
    "title": "My Projects"
})

# Create bookmark in folder
bookmark = await client.call_tool("bookmarks_create", {
    "title": "Project Repository",
    "url": "https://github.com/example/project",
    "parent_id": "folder_id_here"
})

# Update bookmark title
await client.call_tool("bookmarks_update", {
    "bookmark_id": "bookmark_id_here",
    "title": "New Title"
})

# Update bookmark URL
await client.call_tool("bookmarks_update", {
    "bookmark_id": "bookmark_id_here",
    "url": "https://newsite.com"
})

# Rename a folder
await client.call_tool("bookmarks_update", {
    "bookmark_id": "folder_id_here",
    "title": "Renamed Folder"
})
```

### Content Interaction
```python
# Get page text (unlimited)
text = await client.call_tool("content_get_text", {"tab_id": 123})

# Get page text with length limit
text = await client.call_tool("content_get_text", {
    "tab_id": 123,
    "max_length": 1000
})

# Execute JavaScript
result = await client.call_tool("content_execute_script", {
    "tab_id": 123,
    "script": "document.title"
})
```

### Window Management
```python
# List all windows
windows = await client.call_tool("list_windows", {"populate": True})

# Create new window
window = await client.call_tool("create_window", {
    "url": "https://example.com",
    "width": 800,
    "height": 600
})

# Focus window
await client.call_tool("focus_window", {"window_id": 456})
```

For WebSocket protocol details, see [protocol.md](protocol.md).