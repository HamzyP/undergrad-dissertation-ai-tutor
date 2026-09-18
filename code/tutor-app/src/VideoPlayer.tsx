import { useRef, useState, forwardRef, useImperativeHandle } from 'react'

interface VideoPlayerProps {
  src: string
  subtitleSrc?: string
  markers?: number[]
  onTimeUpdate?: (currentTime: number) => void
  onEnded?: () => void
  onDurationChange?: (duration: number) => void
}

export interface VideoPlayerHandle {
  pause: () => void
  play: () => void
  seekTo: (time: number) => void
}

const VideoPlayer = forwardRef<VideoPlayerHandle, VideoPlayerProps>(
  ({ src, subtitleSrc, markers = [], onTimeUpdate, onEnded, onDurationChange }, ref) => {
    const videoRef = useRef<HTMLVideoElement>(null)
    const [isPlaying, setIsPlaying] = useState(false)
    const [currentTime, setCurrentTime] = useState(0)
    const [duration, setDuration] = useState(0)
    const [volume, setVolume] = useState(1)

    useImperativeHandle(ref, () => ({
      pause: () => videoRef.current?.pause(),
      play: () => videoRef.current?.play(),
      seekTo: (time: number) => {
        if (videoRef.current) {
          videoRef.current.currentTime = time
        }
      }
    }))

    const togglePlay = () => {
      if (!videoRef.current) return
      if (isPlaying) {
        videoRef.current.pause()
      } else {
        videoRef.current.play()
      }
    }

    const handleTimeUpdate = () => {
      if (!videoRef.current) return
      setCurrentTime(videoRef.current.currentTime)
      if (onTimeUpdate) {
        onTimeUpdate(videoRef.current.currentTime)
      }
    }

    const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
      if (!videoRef.current) return
      const time = parseFloat(e.target.value)
      videoRef.current.currentTime = time
      setCurrentTime(time)
    }

    const handleVolume = (e: React.ChangeEvent<HTMLInputElement>) => {
      if (!videoRef.current) return
      const vol = parseFloat(e.target.value)
      videoRef.current.volume = vol
      setVolume(vol)
    }

    const toggleFullscreen = () => {
      if (!videoRef.current) return
      if (document.fullscreenElement) {
        document.exitFullscreen()
      } else {
        videoRef.current.requestFullscreen()
      }
    }

    const toggleSubtitles = () => {
      if (!videoRef.current) return
      const track = videoRef.current.textTracks[0]
      if (track) {
        track.mode = track.mode === 'showing' ? 'hidden' : 'showing'
      }
    }

    const formatTime = (seconds: number) => {
      const mins = Math.floor(seconds / 60)
      const secs = Math.floor(seconds % 60)
      return `${mins}:${secs.toString().padStart(2, '0')}`
    }

    return (
    <div className="video-player">
        <video
            ref={videoRef}
            src={src}
            onTimeUpdate={handleTimeUpdate}
            onLoadedMetadata={() => {
            const d = videoRef.current?.duration || 0
            setDuration(d)
            if (onDurationChange) onDurationChange(d)
            }}
            onPlay={() => setIsPlaying(true)}
            onPause={() => setIsPlaying(false)}
            onClick={togglePlay}
            onEnded={onEnded}
            aria-label="Lecture video"
        >

          {subtitleSrc && (
            <track
              kind="subtitles"
              src={subtitleSrc}
              srcLang="en"
              label="English"
              default
            />
          )}
        </video>
        <div className="custom-controls">
          <button onClick={togglePlay} aria-label={isPlaying ? 'Pause' : 'Play'}>
            {isPlaying ? '⏸' : '▶'}
          </button>
          <span className="time-display">{formatTime(currentTime)}</span>
          <div className="seek-container">
            <input
              type="range"
              className="seek-bar"
              min={0}
              max={duration || 0}
              step={0.1}
              value={currentTime}
              onChange={handleSeek}
              aria-label="Seek"
            />
            {duration > 0 && markers.map((time, i) => (
              <div
                key={i}
                className="seek-marker"
                style={{ left: `${(time / duration) * 100}%` }}
                aria-label={`Question at ${formatTime(time)}`}
              />
            ))}
          </div>
          <span className="time-display">{formatTime(duration)}</span>
          <input
            type="range"
            className="volume-bar"
            min={0}
            max={1}
            step={0.05}
            value={volume}
            onChange={handleVolume}
            aria-label="Volume"
          />
          <button onClick={toggleSubtitles} aria-label="Toggle subtitles">
            CC
          </button>
          <button onClick={toggleFullscreen} aria-label="Fullscreen">
            ⛶
          </button>
        </div>
      </div>
    )
  }
)

export default VideoPlayer