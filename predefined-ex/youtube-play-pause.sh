#!/bin/bash

# YouTube Play/Pause Script
# This script generates JavaScript to play or pause a YouTube video
# Usage: youtube-play-pause.sh [play|pause|toggle]
# If no argument provided, it toggles the current state

ACTION="${1:-toggle}"

cat << EOF
(function() {
  // Find the video element and play/pause button
  const video = document.querySelector('video');
  const playPauseButton = document.querySelector('.ytp-play-button');

  if (!video || !playPauseButton) {
    return JSON.stringify({
      success: false,
      error: "Video or play/pause button not found"
    });
  }

  const currentlyPaused = video.paused;
  const buttonLabel = playPauseButton.getAttribute('aria-label') || '';

  let action = '${ACTION}';
  let shouldPlay = false;

  // Determine what action to take
  if (action === 'play') {
    shouldPlay = true;
  } else if (action === 'pause') {
    shouldPlay = false;
  } else if (action === 'toggle') {
    shouldPlay = currentlyPaused;
  }

  // Only click if we need to change the state
  if ((shouldPlay && currentlyPaused) || (!shouldPlay && !currentlyPaused)) {
    playPauseButton.click();

    return JSON.stringify({
      success: true,
      action: shouldPlay ? 'play' : 'pause',
      previousState: currentlyPaused ? 'paused' : 'playing',
      currentTime: video.currentTime,
      duration: video.duration,
      buttonClicked: true
    });
  }

  return JSON.stringify({
    success: true,
    action: 'no_change',
    currentState: currentlyPaused ? 'paused' : 'playing',
    currentTime: video.currentTime,
    duration: video.duration,
    buttonLabel: buttonLabel
  });
})();
EOF