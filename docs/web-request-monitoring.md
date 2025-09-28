# Web Request Monitoring Implementation Plan

## Overview

This document outlines the comprehensive plan for implementing web request interception and monitoring capabilities in FoxMCP. The feature will enable AI assistants to monitor, analyze, and modify web requests in real-time through the Model Context Protocol (MCP).

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
- `requests_stop_monitoring()` - End monitoring and prepare for analysis
- `requests_stop_monitoring_safe()` - Graceful stop with request drainage
- `requests_list_monitors()` - List active monitoring sessions

**Live Monitoring** (Optional real-time feedback):
- `requests_get_recent()` - Get recent requests during monitoring
- `requests_get_status()` - Current monitoring session status
- `requests_get_capabilities()` - Get browser monitoring capabilities

**Request Modification** (Real-time):
- `requests_add_header_rule()` - Modify request headers
- `requests_block_pattern()` - Block requests matching patterns
- `requests_redirect_pattern()` - Redirect requests to different URLs

#### Phase 2: Analysis Session APIs

**Analysis Management**:
- `requests_start_analysis()` - Begin analysis phase of captured data
- `requests_list_analysis_sessions()` - List available analysis sessions
- `requests_create_report()` - Generate comprehensive analysis reports

**Data Retrieval & Search**:
- `requests_search()` - Search captured requests by criteria
- `requests_get_content()` - Get full request/response content
- `requests_query_builder()` - Flexible query interface for complex analysis

**Deep Analysis**:
- `requests_analyze_performance()` - Performance metrics and timing analysis
- `requests_analyze_request_flows()` - Request flow and dependency analysis
- `requests_analyze_error_patterns()` - Deep error pattern investigation
- `requests_compare_timeframes()` - Compare different time periods
- `requests_detect_anomalies()` - Anomaly detection for unusual patterns

**Data Export**:
- `requests_export_data()` - Export analysis data in various formats

## Implementation Phases

### Phase 1: Foundation (Priority: High)

**Extension Updates**:
- Add `webRequest` and `webRequestBlocking` permissions to manifest.json
- Implement basic request interception in background.js
- Create request buffering system with configurable limits
- Add WebSocket communication for monitoring commands

**MCP Server Updates**:
- Add new `_setup_request_monitoring_tools()` category
- Implement session management APIs
- Create request storage and retrieval system
- Add basic monitoring configuration

**Deliverables**:
- Basic request monitoring (start/stop/list)
- Request retrieval with filtering
- URL pattern matching
- Request blocking capability

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
- Anomaly detection algorithms
- Request modification rules
- Header injection/modification
- Response interception and modification

**Deliverables**:
- Intelligent anomaly detection
- Advanced request modification
- Response content modification
- Real-time alerting system

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
requests_stop_monitoring_safe(monitor_id, drain_timeout=5)
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
        "webRequestBlocking",
        "webNavigation",
        "<all_urls>"
    ]
}
```

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
result = await requests_stop_monitoring_safe(monitor["monitor_id"])
print(f"Monitoring complete: {result['total_requests_captured']} requests captured")
```

#### Phase 2: Collaborative Analysis
```python
# Start analysis session
analysis = await requests_start_analysis(
    monitor_id=monitor["monitor_id"],
    analysis_name="API Performance Investigation"
)

# Deep performance analysis
perf = await requests_analyze_performance(analysis["analysis_id"])
print(f"Average response time: {perf['avg_response_time_ms']}ms")

# Search for specific patterns
slow_requests = await requests_query_builder(
    analysis_id=analysis["analysis_id"],
    query={
        "where": {"duration_ms": {"gt": 1000}},
        "order_by": "duration_ms",
        "limit": 5
    }
)

# Analyze request flows
flows = await requests_analyze_request_flows(analysis["analysis_id"])
print("Detected user flows:", flows["flows_detected"])

# Compare different time periods
comparison = await requests_compare_timeframes(
    analysis_id=analysis["analysis_id"],
    timeframe1={"start": "10:30:00", "end": "10:32:00", "label": "Initial load"},
    timeframe2={"start": "10:33:00", "end": "10:35:00", "label": "After changes"}
)

# Generate comprehensive report
report = await requests_create_report(
    analysis_id=analysis["analysis_id"],
    report_type="performance",
    sections=["summary", "timeline", "patterns", "recommendations"]
)
```

### Real-World Analysis Scenarios

#### Scenario 1: Performance Debugging
```python
# User: "This page feels slow, let's investigate"

# Phase 1: Monitor while user navigates
monitor = await requests_start_monitoring(tab_id=123, patterns=["*"])
# User clicks around, navigates pages...
await requests_stop_monitoring_safe(monitor["monitor_id"])

# Phase 2: Analyze captured data
analysis = await requests_start_analysis(monitor["monitor_id"])

# Find performance bottlenecks
slow_requests = await requests_query_builder(analysis["analysis_id"], {
    "where": {"duration_ms": {"gt": 500}},
    "select": ["url", "duration_ms", "method"]
})

# Analyze request dependencies
flows = await requests_analyze_request_flows(analysis["analysis_id"])

# Results: "The /api/dashboard/data endpoint is taking 800ms and blocking the UI"
```

#### Scenario 2: Error Investigation
```python
# User: "I noticed some errors, let's see what's failing"

# Phase 2: Analyze errors in captured data
error_analysis = await requests_analyze_error_patterns(analysis["analysis_id"])

# Search for specific error patterns
failed_requests = await requests_search(analysis["analysis_id"], {
    "status_code_range": [400, 599]
})

# Get full content of failed requests
for request in failed_requests["matches"]:
    content = await requests_get_content(
        analysis["analysis_id"],
        request["request_id"]
    )
    print(f"Failed request: {content['response_content']['body']}")

# Results: "4 requests failed with 404 - invalid user IDs from stale UI data"
```

#### Scenario 3: Before/After Optimization
```python
# User makes code changes during monitoring, then analyzes impact

comparison = await requests_compare_timeframes(
    analysis_id=analysis["analysis_id"],
    timeframe1={"start": "10:30:00", "end": "10:32:00", "label": "Before fix"},
    timeframe2={"start": "10:33:00", "end": "10:35:00", "label": "After fix"}
)

# Results: "Response time improved 33%, error rate reduced 78%"
```

## Claude Code Integration

### Two-Phase User Experience

#### Phase 1: Monitoring Phase Natural Language
- "Monitor API requests while I test this feature"
- "Start capturing network traffic for this tab"
- "Watch for any failed requests while I navigate"
- "Track requests for 2 minutes while I use the app"

#### Phase 2: Analysis Phase Natural Language
- "What were the slowest requests we captured?"
- "Find all POST requests that failed"
- "Show me what happened when I clicked the submit button"
- "Compare performance before and after I made that change"
- "Which endpoints are causing the most delays?"
- "Generate a report of all the API issues we found"

### Collaborative Analysis Workflow

**Data Capture Phase**:
- Minimal interruption to user workflow
- Silent background monitoring with optional status updates
- Real-time request modification (blocking, headers) if needed

**Analysis Phase**:
- Interactive investigation with user-AI collaboration
- Deep dive into captured data with complex queries
- Multiple analysis sessions on same dataset
- Comprehensive reporting and insights

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
- Header modification and blocking rules
- Performance calculation accuracy

### Integration Tests
- Extension ↔ MCP server communication
- Multi-tab monitoring scenarios
- Request modification verification
- Data persistence and retrieval

### Performance Tests
- High-volume request monitoring
- Memory usage with large request histories
- Concurrent monitoring session handling
- Request modification latency impact

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

## Conclusion

The two-phase web request monitoring design provides an optimal balance between efficient data capture and comprehensive analysis capabilities. By separating monitoring from analysis, the system delivers:

- **Reliable data capture** compatible with current Claude Code MCP limitations
- **Rich analysis capabilities** that enable deep investigation and collaboration
- **Flexible workflow** that accommodates both quick checks and thorough investigations
- **Future-proof architecture** that can evolve with improved streaming support

The design prioritizes user experience and practical utility while maintaining technical robustness and compatibility with the existing FoxMCP ecosystem. The comprehensive API surface enables both simple monitoring tasks and complex analytical workflows, making it suitable for developers, performance engineers, and anyone needing to understand web application behavior.