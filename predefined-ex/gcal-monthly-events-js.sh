#!/bin/bash

# Generate JavaScript for Google Calendar Monthly Events Extraction
# Usage: ./gen-monthly-events-js.sh
# Returns: JavaScript that extracts all events grouped by days for current month view

cat << 'EOF'
(function() {
  /**
   * Extract all events from Google Calendar monthly view, grouped by days
   * @returns {Promise<Object>} Events grouped by day with metadata
   */
  function getMonthlyEvents() {
    try {
      const today = new Date();
      const currentMonth = today.getMonth();
      const currentYear = today.getFullYear();
      
      // Get first day of month and calculate offset
      const firstDay = new Date(currentYear, currentMonth, 1);
      const firstDayOfWeek = firstDay.getDay(); // 0 = Sunday
      
      // Get total days in current month
      const lastDay = new Date(currentYear, currentMonth + 1, 0);
      const totalDaysInMonth = lastDay.getDate();
      
      console.log(`Extracting events for ${firstDay.toLocaleString('default', { month: 'long', year: 'numeric' })}`);
      console.log(`First day offset: ${firstDayOfWeek}, Total days: ${totalDaysInMonth}`);
      
      // Find all day containers
      const containers = document.querySelectorAll('.qLWd9c');
      console.log(`Total containers found: ${containers.length}`);
      
      const monthlyEvents = {
        month: firstDay.toLocaleString('default', { month: 'long' }),
        year: currentYear,
        totalDays: totalDaysInMonth,
        firstDayOffset: firstDayOfWeek,
        extractedAt: new Date().toISOString(),
        days: {}
      };
      
      // Process each day of the month
      for (let day = 1; day <= totalDaysInMonth; day++) {
        const containerIndex = firstDayOfWeek + day - 1;
        
        if (containerIndex >= 0 && containerIndex < containers.length) {
          const dayContainer = containers[containerIndex];
          const dayEvents = [];
          
          // Extract all text content from the day container
          const allElements = dayContainer.querySelectorAll('*');
          const processedTexts = new Set(); // Avoid duplicates
          
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
              const timeMatch = text.match(/(\d{1,2}:\d{2}\s*(am|pm))/gi);
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
                .replace(/^[-\s•]+|[-\s•]+$/g, '') // Remove leading/trailing dashes, spaces, bullets
                .replace(/\s+/g, ' ') // Normalize spaces
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
                else if (text.includes('event_busy')) eventInfo.status = 'busy';
                
                // Check for meeting indicators
                if (text.toLowerCase().includes('zoom') || text.toLowerCase().includes('meet')) {
                  eventInfo.meetingType = 'video_call';
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
                const match = timeStr.match(/(\d{1,2}):(\d{2})\s*(am|pm)/i);
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
          
          monthlyEvents.days[day] = {
            date: `${currentYear}-${(currentMonth + 1).toString().padStart(2, '0')}-${day.toString().padStart(2, '0')}`,
            dayOfWeek: new Date(currentYear, currentMonth, day).getDay(),
            containerIndex: containerIndex,
            eventCount: dayEvents.length,
            events: dayEvents
          };
          
        } else {
          console.warn(`Container index ${containerIndex} out of range for day ${day}`);
          monthlyEvents.days[day] = {
            date: `${currentYear}-${(currentMonth + 1).toString().padStart(2, '0')}-${day.toString().padStart(2, '0')}`,
            dayOfWeek: new Date(currentYear, currentMonth, day).getDay(),
            containerIndex: containerIndex,
            eventCount: 0,
            events: [],
            error: 'Container index out of range'
          };
        }
      }
      
      // Calculate summary statistics
      const totalEvents = Object.values(monthlyEvents.days).reduce((sum, day) => sum + day.eventCount, 0);
      const daysWithEvents = Object.values(monthlyEvents.days).filter(day => day.eventCount > 0).length;
      
      monthlyEvents.summary = {
        totalEvents: totalEvents,
        daysWithEvents: daysWithEvents,
        averageEventsPerDay: totalEvents / totalDaysInMonth,
        busiestDay: Object.entries(monthlyEvents.days).reduce((max, [day, data]) => 
          data.eventCount > max.eventCount ? { day: parseInt(day), eventCount: data.eventCount } : max,
          { day: 0, eventCount: 0 }
        )
      };
      
      return Promise.resolve({
        success: true,
        data: monthlyEvents,
        message: `Successfully extracted ${totalEvents} events from ${daysWithEvents} days`
      });
      
    } catch (error) {
      return Promise.resolve({
        success: false,
        error: `Error extracting monthly events: ${error.message}`,
        data: null
      });
    }
  }
  
  // Execute the function immediately
  return getMonthlyEvents();
})();
EOF