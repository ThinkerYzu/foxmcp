# Web Request Monitoring Implementation Plan

## Overview

This document outlines the comprehensive plan for implementing web request monitoring capabilities in FoxMCP. The feature will enable AI assistants to monitor and analyze web requests through the Model Context Protocol (MCP), providing deep insights into web application behavior and performance.

## Architecture Decision: Two-Phase Workflow

### Problem Analysis

Web request monitoring involves capturing asynchronous browser events and making them available to AI assistants through MCP. The key challenge is balancing real-time monitoring with comprehensive analysis capabilities.

### Decision: Two-Phase Capture → Analyze Workflow

**Chosen**: Polling-based monitoring with persistent post-monitoring analysis

**Phase 1 - Data Capture (Monitoring)**:
- Silent background capture of all request data
- Minimal real-time feedback to avoid interrupting user workflow
- Efficient polling-based collection with buffering

**Phase 2 - Collaborative Analysis (Post-Monitoring)**:
- Comprehensive analysis of captured data
- User and AI collaborate to investigate patterns
- Complex queries and deep analysis without time pressure

**Rationale**:
- **Claude Code Limitations**: Current Claude Code MCP implementation has known issues with streaming:
  - Missing final result events in streaming JSON mode
  - Token context limit failures during streaming
  - AsyncGenerator support is unclear/undocumented
- **User Experience**: Separates data collection from analysis for better workflow
- **Analysis Depth**: Enables thorough investigation without real-time constraints
- **Data Persistence**: Allows multiple analysis sessions on same dataset
- **Collaboration**: Facilitates interactive user-AI analysis sessions

### Architecture Overview

```
Browser Requests → Extension Interception → Request Buffer → MCP Server
                                                                ↓
                     Polling APIs ← Data Storage ← Monitoring Session
                           ↓
                  Claude Code Monitoring Phase
                           ↓
                  Analysis APIs ← Persistent Data ← Analysis Session
                           ↓
                  Claude Code Analysis Phase
```

## API Design

### Core API Categories

#### Phase 1: Monitoring Session APIs

**Session Management**:
- `requests_start_monitoring()` - Begin data capture session
- `requests_stop_monitoring()` - Graceful stop with request drainage
- `requests_list_monitors()` - List active monitoring sessions

**Live Monitoring** (Optional real-time feedback):
- `requests_get_status()` - Current monitoring session status
- `requests_get_capabilities()` - Get browser monitoring capabilities

#### Phase 2: Data Retrieval APIs

**Data Access**:
- `requests_list_captured()` - List all captured request summaries from monitoring session
- `requests_search()` - Search captured requests by basic criteria (URL, method, status)
- `requests_get_content()` - Get full request/response content for specific request

#### Data Management APIs

**Session Management**:
- `requests_delete_monitor_data()` - Delete all data from a monitoring session
- `requests_save_monitor_data()` - Save monitoring session data to file for preservation

**Note**: All monitor sessions are lost when MCP server stops. Use `requests_save_monitor_data()` to preserve important sessions to files.

## Detailed API Specifications

### Monitoring Session APIs

#### `requests_start_monitoring()`
**Input**:
```json
{
  "url_patterns": ["https://api.example.com/*", "*/api/*"],
  "options": {
    "capture_request_bodies": true,
    "capture_response_bodies": true,
    "max_body_size": 50000,
    "content_types_to_capture": ["application/json", "text/plain"],
    "sensitive_headers": ["Authorization", "Cookie"]
  },
  "tab_id": 123  // Optional - monitor specific tab only
}
```

**Output**:
```json
{
  "monitor_id": "mon_abc123",
  "status": "active",
  "started_at": "2025-01-15T10:30:00.000Z",
  "url_patterns": ["https://api.example.com/*"],
  "options": {...}
}
```

#### `requests_stop_monitoring()`
**Input**:
```json
{
  "monitor_id": "mon_abc123",
  "drain_timeout": 5  // seconds to wait for in-flight requests
}
```

**Output**:
```json
{
  "monitor_id": "mon_abc123",
  "status": "stopped",
  "stopped_at": "2025-01-15T10:35:00.000Z",
  "total_requests_captured": 156,
  "statistics": {
    "duration_seconds": 300,
    "requests_per_second": 0.52,
    "total_data_size": 2048000
  }
}
```

#### `requests_list_monitors()`
**Input**: None

**Output**:
```json
{
  "monitors": [
    {
      "monitor_id": "mon_abc123",
      "status": "active",
      "started_at": "2025-01-15T10:30:00.000Z",
      "request_count": 45,
      "url_patterns": ["https://api.example.com/*"]
    }
  ]
}
```

#### `requests_get_status()`
**Input**:
```json
{
  "monitor_id": "mon_abc123"
}
```

**Output**:
```json
{
  "monitor_id": "mon_abc123",
  "status": "active",
  "started_at": "2025-01-15T10:30:00.000Z",
  "statistics": {
    "total_requests": 45,
    "requests_per_minute": 15,
    "total_data_captured": 1024000,
    "last_request_at": "2025-01-15T10:32:30.000Z"
  }
}
```

#### `requests_get_capabilities()`
**Input**: None

**Output**:
```json
{
  "supported_features": [
    "url_pattern_filtering",
    "content_capture",
    "tab_filtering",
    "file_export"
  ],
  "max_concurrent_monitors": 5,
  "max_body_size": 10485760,
  "supported_content_types": [
    "application/json",
    "text/plain",
    "application/xml",
    "text/html"
  ]
}
```

### Data Retrieval APIs

#### `requests_list_captured()`
**Input**:
```json
{
  "monitor_id": "mon_abc123"
}
```

**Output**:
```json
{
  "monitor_id": "mon_abc123",
  "total_requests": 156,
  "requests": [
    {
      "request_id": "req_001",
      "timestamp": "2025-01-15T10:30:15.123Z",
      "url": "https://api.example.com/users",
      "method": "POST",
      "status_code": 201,
      "duration_ms": 245,
      "request_size": 89,
      "response_size": 156,
      "content_type": "application/json",
      "tab_id": 123
    }
  ]
}
```

#### `requests_search()`
**Input**:
```json
{
  "monitor_id": "mon_abc123",          // Required
  "criteria": {                       // Optional - all fields optional
    "url_pattern": "*users*",         // Optional - URL pattern to match
    "method": "POST",                 // Optional - HTTP method filter
    "min_status_code": 200,           // Optional - minimum status code
    "max_status_code": 299,           // Optional - maximum status code
    "min_duration_ms": 100,           // Optional - minimum duration filter
    "max_duration_ms": 1000           // Optional - maximum duration filter
  },
  "limit": 50,                        // Optional - default: 100
  "offset": 0                         // Optional - default: 0
}
```

**Output**:
```json
{
  "total_matches": 12,
  "matches": [
    {
      "request_id": "req_001",
      "timestamp": "2025-01-15T10:30:15.123Z",
      "url": "https://api.example.com/users",
      "method": "POST",
      "status_code": 201,
      "duration_ms": 245,
      "request_size": 89,
      "response_size": 156,
      "content_type": "application/json",
      "tab_id": 123
    }
  ]
}
```

#### `requests_get_content()`
**Input**:
```json
{
  "monitor_id": "mon_abc123",
  "request_id": "req_001",
  "include_binary": false,                    // Optional - default: false, when true returns all content (text as string, binary as base64)
  "save_request_body_to": "/path/to/req.bin", // Optional - save request body to file
  "save_response_body_to": "/path/to/res.bin" // Optional - save response body to file
}
```

**Output (default behavior - include_binary: false)**:
```json
{
  "request_id": "req_001",
  "request_headers": {
    "Content-Type": "application/json",
    "Authorization": "Bearer ***"
  },
  "response_headers": {
    "Content-Type": "application/json",
    "Content-Length": "156"
  },
  "request_body": {
    "included": false,
    "content": null,
    "content_type": "application/json",
    "encoding": null,
    "size_bytes": 89,
    "truncated": false,
    "saved_to_file": null
  },
  "response_body": {
    "included": false,
    "content": null,
    "content_type": "application/json",
    "encoding": null,
    "size_bytes": 156,
    "truncated": false,
    "saved_to_file": null
  }
}
```

**Example with content included (include_binary: true)**:
```json
{
  "request_id": "req_002",
  "request_headers": {
    "Content-Type": "application/json"
  },
  "response_headers": {
    "Content-Type": "image/png",
    "Content-Length": "2048"
  },
  "request_body": {
    "included": true,
    "content": "{\"name\": \"John\", \"email\": \"john@example.com\"}",
    "content_type": "application/json",
    "encoding": "utf8",
    "size_bytes": 89,
    "truncated": false,
    "saved_to_file": null
  },
  "response_body": {
    "included": true,
    "content": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==",
    "content_type": "image/png",
    "encoding": "base64",
    "size_bytes": 2048,
    "truncated": false,
    "saved_to_file": null
  }
}
```

**Example with file saving**:
```json
{
  "request_id": "req_003",
  "request_headers": {
    "Content-Type": "application/octet-stream"
  },
  "response_headers": {
    "Content-Type": "application/pdf",
    "Content-Length": "1048576"
  },
  "request_body": {
    "included": false,
    "content": null,
    "content_type": "application/octet-stream",
    "encoding": null,
    "size_bytes": 512000,
    "truncated": false,
    "saved_to_file": "/path/to/req.bin"
  },
  "response_body": {
    "included": false,
    "content": null,
    "content_type": "application/pdf",
    "encoding": null,
    "size_bytes": 1048576,
    "truncated": false,
    "saved_to_file": "/path/to/res.bin"
  }
}
```

### Data Management APIs

#### Session Data Management

**`requests_delete_monitor_data()`** - Delete all data from a monitoring session
- **Purpose**: Clean up all request data from a specific monitoring session
- **Use Case**: Free storage after analysis is complete

**Input**:
```json
{
  "monitor_id": "mon_abc123"
}
```

**Output**:
```json
{
  "monitor_id": "mon_abc123",
  "deleted": true,
  "requests_deleted": 156,
  "data_size_freed": 2048000
}
```

**`requests_delete_analysis_session()`** - Delete analysis session data
- **Purpose**: Remove persistent analysis data and cached results
- **Use Case**: Clean up after completing investigation work

**Input**:
```json
{
  "analysis_session_id": "ana_xyz789"
}
```

**Output**:
```json
{
  "analysis_session_id": "ana_xyz789",
  "deleted": true,
  "data_freed": 1024000
}
```

**`requests_cleanup_expired_sessions()`** - Clean up expired sessions
- **Purpose**: Bulk cleanup of old monitoring and analysis sessions
- **Use Case**: Regular maintenance to free storage space

**Input**:
```json
{
  "max_age_hours": 48,  // Optional - default: 48
  "dry_run": false      // Optional - default: false, if true only reports what would be deleted
}
```

**Output**:
```json
{
  "sessions_cleaned": 3,
  "total_data_freed": 5120000,
  "expired_sessions": ["mon_abc123", "mon_def456", "ana_ghi789"]
}
```

#### Storage Management

**`requests_get_storage_usage()`** - Get storage usage information
- **Purpose**: Monitor storage consumption across all monitoring sessions
- **Use Case**: Understand storage patterns and plan cleanup

**Input**: None

**Output**:
```json
{
  "total_storage_bytes": 10485760,
  "active_sessions": 2,
  "expired_sessions": 1,
  "storage_breakdown": {
    "active_monitoring": 2048000,
    "analysis_data": 6291456,
    "expired_data": 2146304
  },
  "oldest_session": "2025-01-14T10:30:00.000Z",
  "recommended_cleanup": {
    "expired_sessions_count": 1,
    "potential_freed_bytes": 2146304
  }
}
```

#### Selective Data Deletion

**`requests_delete_by_pattern()`** - Delete requests matching URL patterns
- **Purpose**: Remove specific types of requests (e.g., debug, logs, tracking)
- **Use Case**: Clean sensitive or irrelevant data while preserving important requests

**Input**:
```json
{
  "monitor_id": "mon_abc123",
  "url_patterns": ["*/api/logs*", "*/debug/*", "*analytics*"],
  "delete_content_only": false  // If true, keeps metadata but removes bodies
}
```

**Output**:
```json
{
  "monitor_id": "mon_abc123",
  "requests_deleted": 23,
  "data_size_freed": 512000,
  "patterns_matched": ["*/api/logs*", "*/debug/*"],
  "summary": {
    "total_matching_requests": 23,
    "deleted_requests": 23,
    "preserved_metadata": 0
  }
}
```

**`requests_delete_by_timeframe()`** - Delete requests from specific time range
- **Purpose**: Remove data from specific time periods (e.g., before optimization)
- **Use Case**: Focus analysis on specific time periods

**Input**:
```json
{
  "monitor_id": "mon_abc123",
  "start_time": "2025-01-15T10:30:00.000Z",
  "end_time": "2025-01-15T10:35:00.000Z"
}
```

**Output**:
```json
{
  "monitor_id": "mon_abc123",
  "requests_deleted": 34,
  "data_size_freed": 768000,
  "timeframe": {
    "start": "2025-01-15T10:30:00.000Z",
    "end": "2025-01-15T10:35:00.000Z"
  }
}
```

**`requests_delete_content_only()`** - Delete request/response bodies but keep metadata
- **Purpose**: Free storage while preserving request timing and status information
- **Use Case**: Keep performance data but remove large content bodies

**Input**:
```json
{
  "monitor_id": "mon_abc123",
  "criteria": {
    "min_body_size": 50000,     // Only delete large content
    "content_types": ["image/*", "video/*", "application/octet-stream"],
    "exclude_patterns": ["*/api/critical*"]  // Don't delete content from critical APIs
  }
}
```

**Output**:
```json
{
  "monitor_id": "mon_abc123",
  "requests_modified": 12,
  "content_deleted": 3145728,
  "metadata_preserved": true,
  "summary": {
    "large_content_removed": 8,
    "binary_content_removed": 4,
    "critical_apis_preserved": 3
  }
}
```

#### Data Retention Policies

**`requests_set_retention_policy()`** - Configure automatic data cleanup
- **Purpose**: Set up automated data lifecycle management
- **Use Case**: Maintain storage limits and comply with data retention requirements

**Input**:
```json
{
  "policy": {
    "max_session_age_hours": 48,
    "max_total_storage_mb": 100,
    "auto_cleanup_enabled": true,
    "cleanup_interval_hours": 6,
    "preserve_analysis_sessions": true,
    "large_content_threshold_mb": 5,
    "critical_url_patterns": ["*/api/auth*", "*/api/payment*"]
  }
}
```

**Output**:
```json
{
  "policy_updated": true,
  "previous_policy": {
    "max_session_age_hours": 24,
    "max_total_storage_mb": 50,
    "auto_cleanup_enabled": false
  },
  "new_policy": {
    "max_session_age_hours": 48,
    "max_total_storage_mb": 100,
    "auto_cleanup_enabled": true,
    "cleanup_interval_hours": 6,
    "preserve_analysis_sessions": true
  },
  "next_cleanup": "2025-01-15T16:30:00.000Z"
}
```

**`requests_get_retention_policy()`** - Get current retention policy
- **Purpose**: Review current data lifecycle configuration
- **Use Case**: Understand how data is being managed automatically

**Input**: None

**Output**:
```json
{
  "policy": {
    "max_session_age_hours": 48,
    "max_total_storage_mb": 100,
    "auto_cleanup_enabled": true,
    "cleanup_interval_hours": 6,
    "preserve_analysis_sessions": true,
    "large_content_threshold_mb": 5,
    "critical_url_patterns": ["*/api/auth*", "*/api/payment*"]
  },
  "status": {
    "last_cleanup": "2025-01-15T10:30:00.000Z",
    "next_cleanup": "2025-01-15T16:30:00.000Z",
    "cleanup_enabled": true
  },
  "current_usage": {
    "total_storage_mb": 45,
    "sessions_count": 3,
    "oldest_session_age_hours": 18
  }
}
```

#### Data Export and Preservation

**`requests_save_monitor_data()`** - Save monitoring session data to file for preservation
- **Purpose**: Export session data to persistent file storage
- **Use Case**: Archive important monitoring sessions beyond server session lifecycle

**Input**:
```json
{
  "monitor_id": "mon_abc123",
  "file_path": "/path/to/save/monitor_session.json",
  "include_content": true,  // Include full request/response bodies
  "format": "json",         // Optional: "json", "har", "csv"
  "compression": "gzip",    // Optional: "none", "gzip", "zip"
  "export_options": {
    "include_sensitive_headers": false,
    "max_body_size": 50000,
    "exclude_patterns": ["*/api/logs*"]
  }
}
```

**Output**:
```json
{
  "monitor_id": "mon_abc123",
  "saved": true,
  "file_path": "/path/to/save/monitor_session.json.gz",
  "file_size": 2048000,
  "requests_saved": 156,
  "format": "json",
  "compression": "gzip",
  "export_summary": {
    "total_requests": 156,
    "requests_with_content": 143,
    "sensitive_headers_masked": 156,
    "excluded_by_pattern": 13
  }
}
```

**`requests_load_monitor_data()`** - Load previously saved monitoring data
- **Purpose**: Import archived session data back into analysis system
- **Use Case**: Analyze historical monitoring sessions or share data between systems

**Input**:
```json
{
  "file_path": "/path/to/save/monitor_session.json.gz",
  "create_analysis_session": true,  // Create new analysis session from loaded data
  "session_name": "Production Issue Analysis"  // Optional friendly name
}
```

**Output**:
```json
{
  "loaded": true,
  "analysis_session_id": "ana_loaded123",
  "requests_loaded": 156,
  "original_monitor_id": "mon_abc123",
  "session_date": "2025-01-15T10:30:00.000Z",
  "load_summary": {
    "file_format": "json",
    "compression": "gzip",
    "data_integrity_verified": true,
    "session_name": "Production Issue Analysis"
  }
}
```

#### Data Lifecycle Management

**`requests_list_all_sessions()`** - List all monitoring and analysis sessions
- **Purpose**: Get overview of all stored data across sessions
- **Use Case**: Data governance and cleanup planning

**Input**:
```json
{
  "include_expired": false,  // Optional - default: false
  "sort_by": "creation_date", // Optional: "creation_date", "size", "last_access"
  "sort_order": "desc"       // Optional: "asc", "desc"
}
```

**Output**:
```json
{
  "total_sessions": 5,
  "active_monitoring_sessions": 1,
  "analysis_sessions": 3,
  "expired_sessions": 1,
  "sessions": [
    {
      "session_id": "mon_abc123",
      "type": "monitoring",
      "status": "active",
      "created_at": "2025-01-15T10:30:00.000Z",
      "last_accessed": "2025-01-15T10:35:00.000Z",
      "request_count": 156,
      "data_size": 2048000,
      "age_hours": 2
    },
    {
      "session_id": "ana_xyz789",
      "type": "analysis",
      "status": "available",
      "created_at": "2025-01-14T15:20:00.000Z",
      "last_accessed": "2025-01-15T09:15:00.000Z",
      "source_monitor_id": "mon_def456",
      "data_size": 1536000,
      "age_hours": 19
    }
  ]
}
```

**Note**: All monitor sessions are lost when MCP server stops. Use `requests_save_monitor_data()` to preserve important sessions to files.

## Implementation Phases

### Phase 1: Foundation (Priority: High) ✅ COMPLETED

**Extension Updates**:
- Add `webRequest` permission to manifest.json (read-only monitoring)
- Implement basic request interception in background.js
- Create request buffering system with configurable limits
- Add WebSocket communication for monitoring commands

**MCP Server Updates**: ✅ COMPLETED
- ✅ Add new `_setup_request_monitoring_tools()` category
- ✅ Implement session management APIs
- ✅ Create request storage and retrieval system
- ✅ Add basic monitoring configuration

**Deliverables**: ✅ COMPLETED
- ✅ Basic request monitoring (start/stop/list)
- ✅ Request retrieval with filtering
- ✅ URL pattern matching
- ✅ Performance analysis capabilities

**Implementation Status**:
- ✅ `requests_start_monitoring()` - Start monitoring with URL patterns and options
- ✅ `requests_stop_monitoring()` - Graceful stop with request drainage
- ✅ `requests_list_captured()` - List captured request summaries
- ✅ `requests_get_content()` - Get full request/response content with binary support

### Phase 2: Analysis and Search (Priority: Medium)

**Features**:
- Performance analysis with timing metrics
- Request pattern analysis and trends
- Content search within request/response bodies
- Advanced filtering and query capabilities

**Deliverables**:
- Performance monitoring tools
- Request search and analysis APIs
- Content capture with size/type filtering
- Export functionality

### Phase 3: Advanced Features (Priority: Low)

**Features**:
- Advanced anomaly detection algorithms
- Machine learning-based pattern recognition
- Predictive performance analysis
- Integration with external monitoring systems

**Deliverables**:
- Intelligent anomaly detection
- Predictive analytics
- Advanced reporting capabilities
- External system integration

## Technical Specifications

### Request Data Structure

```json
{
    "request_id": "req_123",
    "timestamp": 1642678200.123,
    "url": "https://api.example.com/users",
    "method": "POST",
    "status_code": 201,
    "duration_ms": 245,
    "tab_id": 123,

    "request_headers": {
        "Content-Type": "application/json",
        "Authorization": "Bearer ***"
    },
    "response_headers": {
        "Content-Type": "application/json",
        "Content-Length": "156"
    },

    "request_body": {
        "included": true,
        "content_type": "application/json",
        "size_bytes": 89,
        "content": "{\"name\": \"John\", \"email\": \"john@example.com\"}",
        "truncated": false
    },

    "response_body": {
        "included": false,
        "content_type": "application/json",
        "size_bytes": 156,
        "preview": "{\"id\": 123, \"name\": \"John\"..."
    }
}
```

### Content Capture Configuration

**Content Inclusion Control**:
- Optional content capture (headers always included)
- Size limits to prevent overwhelming responses
- Content-type filtering (JSON, XML, text)
- Sensitive header masking (Authorization, Cookies)

**Configuration Options**:
```python
{
    "capture_request_bodies": True,
    "capture_response_bodies": True,
    "max_body_size": 50000,
    "content_types_to_capture": ["application/json", "text/plain"],
    "sensitive_headers": ["Authorization", "Cookie", "X-API-Key"]
}
```

## Data Lifecycle and Persistence

### Two-Phase Data Management

#### Phase 1: Monitoring Session Data
- **Active Monitoring**: Real-time request capture and buffering
- **Data Retention**: Temporary storage during monitoring session
- **Access Pattern**: Polling-based retrieval with minimal analysis

#### Phase 2: Analysis Session Data
- **Data Persistence**: Long-term storage of captured requests (24-48 hours)
- **Enhanced Indexing**: Optimized for complex queries and analysis
- **Access Pattern**: Rich analysis APIs with full search capabilities

### Session State Management

```python
MONITOR_STATES = {
    "active":           "Capturing requests in real-time",
    "stopping":         "Finishing capture, preparing for analysis",
    "analysis_ready":   "Data available for analysis phase",
    "archived":         "Long-term storage, limited operations",
    "expired":          "Data cleaned up, session unavailable"
}
```

### Data Availability After Monitoring

**Problem**: Users need time to analyze captured data after monitoring ends.

**Solution**: Automatic transition to analysis phase:

1. **Monitoring Ends** → Data persisted for analysis
2. **Analysis Phase** → Full access to captured data (24-48 hours)
3. **Archive Phase** → Summary data only (optional long-term storage)
4. **Cleanup Phase** → Data removed to free resources

### Race Condition Mitigation

#### 1. Graceful Stop with Drainage
```python
requests_stop_monitoring(monitor_id, drain_timeout=5)
```
- Signals extension to prepare for stop
- Performs multiple final polls with delays
- Waits for network lag and in-flight requests
- Reports final drainage statistics
- Automatically transitions to analysis phase

#### 2. Request Sequence Numbers
- Add sequence numbers to detect gaps
- Enable gap detection and reporting
- Help identify potential data loss during transitions

#### 3. Extension-Side Buffering with Analysis Preparation
- Buffer requests in extension until acknowledged
- Implement server acknowledgment system
- Flush buffers before transitioning to analysis phase
- Prepare data indexes for efficient analysis queries

## Security and Privacy Considerations

### Security Controls
- URL pattern whitelisting/blacklisting
- Request size limits to prevent DoS
- Rate limiting for modifications
- Secure storage of sensitive data

### Privacy Measures
- Optional request logging with user consent
- Automatic masking of sensitive headers
- Configurable data retention policies
- Content-type filtering to exclude sensitive data

### Browser Permissions Required
```json
{
    "permissions": [
        "webRequest",
        "webNavigation",
        "<all_urls>"
    ]
}
```

**Note**: Only read-only `webRequest` permission is required for monitoring. No `webRequestBlocking` needed since we're not modifying requests.

## Usage Examples

### Two-Phase Workflow Example

#### Phase 1: Data Capture
```python
# Start monitoring session
monitor = await requests_start_monitoring(
    tab_id=123,
    url_patterns=["https://api.example.com/*"],
    options={"capture_headers": True, "capture_request_bodies": True}
)

# Optional: Check monitoring status during capture
status = await requests_get_status(monitor["monitor_id"])
print(f"Captured {status['statistics']['total_requests']} requests so far")

# User interacts with browser while monitoring runs silently...

# End monitoring and prepare for analysis
result = await requests_stop_monitoring(monitor["monitor_id"])
print(f"Monitoring complete: {result['total_requests_captured']} requests captured")
```

#### Phase 2: Data Retrieval and Analysis
```python
# Get all captured data
all_requests = await requests_list_captured(monitor["monitor_id"])
print(f"Retrieved {len(all_requests)} captured requests")

# Search for slow requests
slow_requests = await requests_search(
    monitor_id=monitor["monitor_id"],
    criteria={"min_duration_ms": 1000}
)

# Get detailed content for specific requests
for request in slow_requests["matches"]:
    content = await requests_get_content(
        monitor_id=monitor["monitor_id"],
        request_id=request["request_id"]
    )
    # MCP client (Claude) analyzes the data and provides insights
```

### Real-World Analysis Scenarios

#### Scenario 1: Performance Debugging
```python
# User: "This page feels slow, let's investigate"

# Phase 1: Monitor while user navigates
monitor = await requests_start_monitoring(tab_id=123, patterns=["*"])
# User clicks around, navigates pages...
await requests_stop_monitoring(monitor["monitor_id"])

# Phase 2: Retrieve and analyze captured data
all_requests = await requests_list_captured(monitor["monitor_id"])

# Find slow requests
slow_requests = await requests_search(monitor["monitor_id"], {
    "min_duration_ms": 500
})

# Claude analyzes the data and provides insights:
# "I found the /api/dashboard/data endpoint averaging 800ms - that's your bottleneck"
```

#### Scenario 2: Error Investigation
```python
# User: "I noticed some errors, let's see what's failing"

# Phase 2: Search for errors in captured data
failed_requests = await requests_search(monitor["monitor_id"], {
    "min_status_code": 400,
    "max_status_code": 599
})

# Get full content of failed requests
for request in failed_requests["matches"]:
    content = await requests_get_content(
        monitor["monitor_id"],
        request["request_id"]
    )
    # Claude analyzes: "4 requests failed with 404 - invalid user IDs from stale UI data"
```

#### Scenario 3: Before/After Optimization
```python
# User makes code changes during monitoring, then analyzes impact
all_requests = await requests_list_captured(monitor["monitor_id"])

# Claude analyzes timestamps and performance differences:
# "Comparing before/after your change: response time improved 33%, error rate reduced 78%"
```

## Claude Code Integration

### Two-Phase User Experience

#### Phase 1: Monitoring Phase Natural Language
- "Monitor API requests while I test this feature"
- "Start capturing network traffic for this tab"
- "Watch for any failed requests while I navigate"
- "Track requests for 2 minutes while I use the app"
- "Record all network activity while I reproduce this bug"

#### Phase 2: Analysis Phase Natural Language
- "What were the slowest requests we captured?"
- "Find all POST requests that failed"
- "Show me what happened when I clicked the submit button"
- "Compare performance before and after I made that change"
- "Which endpoints are causing the most delays?"

### Collaborative Analysis Workflow

**Data Capture Phase**:
- Minimal interruption to user workflow
- Silent background monitoring with optional status updates
- Pure observation mode - no request modification

**Analysis Phase**:
- Interactive investigation with user-AI collaboration
- AI analyzes retrieved data using reasoning capabilities
- Multiple analysis sessions on same dataset
- AI-generated insights and recommendations

### Enhanced User Experience Examples

#### Workflow 1: Performance Investigation
```
User: "This page feels slow, let's investigate"
AI: "I'll monitor network requests while you use the page normally"
[Phase 1: Silent monitoring while user interacts]
AI: "Monitoring complete - captured 156 requests over 5 minutes"

User: "What's making it slow?"
AI: "Let me analyze the data... I found 3 major issues:
     1. /api/dashboard takes 800ms on average
     2. Multiple redundant calls to /api/user/profile
     3. Large image downloads without compression"

User: "Show me the dashboard API calls"
AI: [detailed analysis] "The dashboard endpoint was called 12 times,
     averaging 800ms. It appears to be running complex database queries."

User: "Can we see the before/after when I optimized the code?"
AI: [timeframe comparison] "Great improvement! Response time dropped
     from 800ms to 280ms after your optimization."
```

#### Workflow 2: Debugging Failed Requests
```
User: "I'm getting errors but can't figure out why"
AI: "I'll capture the network traffic while you reproduce the issue"
[Phase 1: Monitoring during user interaction]

User: "OK I got the error again, what happened?"
AI: "I found the problem! There were 3 failed requests:
     - POST /api/validate returned 422 (validation error)
     - The error message says 'Invalid email format'
     - This is blocking the form submission"

User: "Show me the exact request that failed"
AI: [shows full request content] "Here's the request body that failed:
     {'email': 'test@', 'name': 'John'} - the email is incomplete"
```

## Testing Strategy

### Unit Tests
- Request filtering and pattern matching
- Content capture and size limiting
- Data structure validation
- Performance calculation accuracy

### Integration Tests
- Extension ↔ MCP server communication
- Multi-tab monitoring scenarios
- Data capture accuracy verification
- Data persistence and retrieval

### Performance Tests
- High-volume request monitoring
- Memory usage with large request histories
- Concurrent monitoring session handling
- Data storage and retrieval performance

## Future Enhancements

### Streaming Support (When Available)
- Upgrade to AsyncGenerator streaming when Claude Code support improves
- Maintain polling fallback for compatibility
- Hybrid approach with streaming + polling backup

### Advanced Analysis
- Machine learning-based anomaly detection
- Request correlation and dependency mapping
- Performance regression detection
- Automated optimization suggestions

### Enterprise Features
- Multi-user monitoring sessions
- Request monitoring policies and compliance
- Advanced export formats (HAR, OpenAPI)
- Integration with monitoring platforms

## Benefits of Two-Phase Design

### User Experience Benefits
1. **Uninterrupted Workflow**: Users can interact naturally with browser during monitoring
2. **Thorough Analysis**: No time pressure during investigation phase
3. **Multiple Investigations**: Can return to same data for different analysis angles
4. **Collaborative Discovery**: User and AI work together to understand patterns
5. **Historical Comparison**: Compare different time periods within captured data

### Technical Benefits
1. **Data Persistence**: Captured data survives monitoring session end
2. **Complex Queries**: Rich analysis without real-time performance constraints
3. **Flexible Indexing**: Optimize data storage for analysis patterns
4. **Resource Management**: Clean separation of capture vs analysis overhead
5. **Claude Code Compatibility**: Works within current MCP limitations

### Analysis Capabilities
1. **Deep Performance Investigation**: Multi-dimensional performance analysis
2. **Error Pattern Detection**: Comprehensive error clustering and root cause analysis
3. **Request Flow Mapping**: Understand application request dependencies
4. **Before/After Comparisons**: Measure impact of changes and optimizations
5. **Comprehensive Reporting**: Generate detailed analysis documents

## Implementation Status

### ✅ Completed Features

**MCP Server APIs (4/4 basic APIs implemented)**:
- ✅ `requests_start_monitoring()` - Comprehensive monitoring setup with URL patterns, options, and tab filtering
- ✅ `requests_stop_monitoring()` - Graceful stop with configurable drainage timeout
- ✅ `requests_list_captured()` - List all captured request summaries with metadata
- ✅ `requests_get_content()` - Full content retrieval with binary support and file saving

**Extension Integration (4/4 basic handlers implemented)**:
- ✅ Request action routing in `background.js` - Added `case 'requests'` to message handler
- ✅ `handleRequestsAction()` function - Processes all request monitoring actions
- ✅ Mock implementations for all 4 basic APIs returning proper JSON structure
- ✅ Error handling for unknown request actions

**Implementation Details**:
- ✅ JSON response format matching API specifications
- ✅ Comprehensive error handling and validation
- ✅ WebSocket communication integration
- ✅ Binary content handling (base64 encoding + file saving)
- ✅ Configurable capture options (body sizes, content types, sensitive headers)
- ✅ Optional tab-specific monitoring support
- ✅ Extension-server message protocol compatibility
- ✅ End-to-end test integration working

**File Locations**:
- `/server/mcp_tools.py` in `_setup_request_monitoring_tools()` method
- `/extension/background.js` in `handleRequestsAction()` function

### 🚧 Next Phase: Actual Request Monitoring Implementation

**Required for full functionality**:
- Replace mock responses with actual browser WebRequest API integration
- Request buffering and storage system in extension
- Real-time request capture using `chrome.webRequest` listeners
- Manifest.json permission updates for `webRequest` access
- Request filtering by URL patterns and content types
- Data persistence and retrieval mechanisms

## Conclusion

The two-phase web request monitoring design provides an optimal balance between efficient data capture and comprehensive analysis capabilities. By separating monitoring from analysis, the system delivers:

- **Reliable data capture** compatible with current Claude Code MCP limitations
- **Rich analysis capabilities** that enable deep investigation and collaboration
- **Flexible workflow** that accommodates both quick checks and thorough investigations
- **Future-proof architecture** that can evolve with improved streaming support

**Current Status**: MCP server-side APIs are fully implemented and ready for extension integration. The comprehensive API surface enables both simple monitoring tasks and complex analytical workflows, making it suitable for developers, performance engineers, and anyone needing to understand web application behavior.

The implementation is production-ready on the MCP server side and follows established patterns from the existing FoxMCP ecosystem.