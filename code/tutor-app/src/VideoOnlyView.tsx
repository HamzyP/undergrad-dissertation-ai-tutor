import { useState, useRef } from 'react'
import VideoPlayer from './VideoPlayer'
import type { VideoPlayerHandle } from './VideoPlayer'

interface VideoOnlyViewProps {
  participantId: string
  videoSrc: string
  subtitleSrc?: string
  onComplete: () => void
}

function VideoOnlyView({ participantId, videoSrc, subtitleSrc, onComplete }: VideoOnlyViewProps) {
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const playerRef = useRef<VideoPlayerHandle>(null)

  const showFinishedButton = duration > 0 && currentTime >= duration - 30

  return (
    <main className="video-only-view">
      <section className="video-panel" aria-label="Video">
        <div className="participant-id-badge" aria-label={`Participant ID: ${participantId}`}>
          ID: <strong>{participantId}</strong>
        </div>
        <VideoPlayer
          ref={playerRef}
          src={videoSrc}
          subtitleSrc={subtitleSrc}
          onTimeUpdate={setCurrentTime}
          onDurationChange={setDuration}
          onEnded={onComplete}
        />
        {showFinishedButton && (
          <button className="finished-button" onClick={onComplete}>
            I'm finished — continue
          </button>
        )}
      </section>
    </main>
  )
}

export default VideoOnlyView