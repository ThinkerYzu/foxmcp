#!/bin/bash

# Generate JavaScript for Google Calendar Daily Events Extraction
# Usage: ./gen-daily-events-js.sh day [month] [year]
# Example: ./gen-daily-events-js.sh 8
# Example: ./gen-daily-events-js.sh 15 9 2025

if [ $# -lt 1 ] || [ $# -gt 3 ]; then
    echo "Usage: $0 day [month] [year]"
    echo "Examples:"
    echo "  $0 8                    # September 8, 2025 (current month/year)"
    echo "  $0 15 10               # October 15, 2025 (current year)"
    echo "  $0 25 12 2024          # December 25, 2024"
    exit 1
fi

DAY="$1"
MONTH="${2:-9}"    # Default to September (9)
YEAR="${3:-2025}"  # Default to 2025

cat << EOF
(function() {
  /**
   * Extract events for a specific date from Google Calendar monthly view
   * @param {number} targetDay - Day of the month (1-31)
   * @param {number} targetMonth - Month (1-12)
   * @param {number} targetYear - Year (e.g., 2025)
   * @returns {Promise<Object>} Events for the specified date
   */
  function getDailyEvents(targetDay, targetMonth, targetYear) {
    try {
      console.log(\`Extracting events for \${targetMonth}/\${targetDay}/\${targetYear}\`);
      
      // Calculate container index for the target date
      const firstDay = new Date(targetYear, targetMonth - 1, 1);
      const firstDayOfWeek = firstDay.getDay(); // 0 = Sunday
      const containerIndex = firstDayOfWeek + targetDay - 1;
      
      console.log(\`First day of month offset: \${firstDayOfWeek}\`);
      console.log(\`Target container index: \${containerIndex}\`);
      
      // Find all day containers
      const containers = document.querySelectorAll('.qLWd9c');
      console.log(\`Total containers found: \${containers.length}\`);
      
      if (containerIndex < 0 || containerIndex >= containers.length) {
        return Promise.resolve({
          success: false,
          error: \`Invalid date or container index \${containerIndex} out of range (0-\${containers.length-1})\`,
          date: \`\${targetYear}-\${targetMonth.toString().padStart(2, '0')}-\${targetDay.toString().padStart(2, '0')}\`,
          containerIndex: containerIndex,
          totalContainers: containers.length
        });
      }
      
      const dayContainer = containers[containerIndex];
      const dayEvents = [];
      
      // Extract all text content from the day container
      const allElements = dayContainer.querySelectorAll('*');
      const processedTexts = new Set(); // Avoid duplicates
      
      console.log(\`Found \${allElements.length} elements in day container\`);
      
      for (let element of allElements) {
        const text = element.textContent?.trim();
        
        if (text && 
            (text.includes('am') || text.includes('pm') || 
             text.includes('meeting') || text.includes('standup') || 
             text.includes('1:1') || text.includes(':')) &&
            text.length > 2 && text.length < 200 &&
            !processedTexts.has(text)) {
          
          processedTexts.add(text);
          
          // Try to parse time information
          const timeMatch = text.match(/(\\d{1,2}:\\d{2}\\s*(am|pm))/gi);
          const hasTimeInfo = timeMatch !== null;
          
          // Extract event title (remove time information)
          let eventTitle = text;
          if (timeMatch) {
            timeMatch.forEach(time => {
              eventTitle = eventTitle.replace(time, '').trim();
            });
          }
          
          // Clean up common suffixes/prefixes
          eventTitle = eventTitle
            .replace(/^[-\\s•]+|[-\\s•]+\$/g, '') // Remove leading/trailing dashes, spaces, bullets
            .replace(/\\s+/g, ' ') // Normalize spaces
            .trim();
          
          if (eventTitle && eventTitle.length > 0) {
            const eventInfo = {
              title: eventTitle,
              rawText: text,
              times: timeMatch || [],
              hasTimeInfo: hasTimeInfo,
              element: {
                tagName: element.tagName,
                className: element.className,
                hasClickableClass: element.className.includes('WBi6vc') || element.className.includes('nHqeVd')
              }
            };
            
            // Check for status indicators
            if (text.includes('Needs RSVP')) eventInfo.rsvpStatus = 'needs_rsvp';
            else if (text.includes('Accepted')) eventInfo.rsvpStatus = 'accepted';
            else if (text.includes('Tentative')) eventInfo.rsvpStatus = 'tentative';
            else if (text.includes('event_busy')) eventInfo.status = 'busy';
            
            // Check for meeting indicators
            if (text.toLowerCase().includes('zoom') || text.toLowerCase().includes('meet')) {
              eventInfo.meetingType = 'video_call';
            }
            
            // Extract location if present
            const locationMatch = text.match(/Location:\\s*([^,]+)/);
            if (locationMatch) {
              eventInfo.location = locationMatch[1].trim();
            }
            
            dayEvents.push(eventInfo);
          }
        }
      }
      
      // Sort events by time if available
      dayEvents.sort((a, b) => {
        if (a.times.length > 0 && b.times.length > 0) {
          const timeA = a.times[0].toLowerCase();
          const timeB = b.times[0].toLowerCase();
          
          // Convert to 24-hour format for comparison
          const parseTime = (timeStr) => {
            const match = timeStr.match(/(\\d{1,2}):(\\d{2})\\s*(am|pm)/i);
            if (match) {
              let hours = parseInt(match[1]);
              const minutes = parseInt(match[2]);
              const isPM = match[3].toLowerCase() === 'pm';
              
              if (isPM && hours !== 12) hours += 12;
              if (!isPM && hours === 12) hours = 0;
              
              return hours * 60 + minutes;
            }
            return 0;
          };
          
          return parseTime(timeA) - parseTime(timeB);
        }
        
        // If no times, sort by title
        return a.title.localeCompare(b.title);
      });
      
      // Create response object
      const response = {
        success: true,
        date: \`\${targetYear}-\${targetMonth.toString().padStart(2, '0')}-\${targetDay.toString().padStart(2, '0')}\`,
        dayOfWeek: new Date(targetYear, targetMonth - 1, targetDay).getDay(),
        dayName: new Date(targetYear, targetMonth - 1, targetDay).toLocaleDateString('en-US', { weekday: 'long' }),
        monthName: new Date(targetYear, targetMonth - 1, targetDay).toLocaleDateString('en-US', { month: 'long' }),
        containerIndex: containerIndex,
        eventCount: dayEvents.length,
        events: dayEvents,
        extractedAt: new Date().toISOString(),
        message: \`Successfully extracted \${dayEvents.length} events for \${targetMonth}/\${targetDay}/\${targetYear}\`
      };
      
      console.log(\`Extracted \${dayEvents.length} events for the day\`);
      
      return Promise.resolve(response);
      
    } catch (error) {
      return Promise.resolve({
        success: false,
        error: \`Error extracting daily events: \${error.message}\`,
        date: \`\${targetYear}-\${targetMonth.toString().padStart(2, '0')}-\${targetDay.toString().padStart(2, '0')}\`,
        data: null
      });
    }
  }
  
  // Execute the function with provided parameters
  return getDailyEvents(${DAY}, ${MONTH}, ${YEAR});
})();
EOF