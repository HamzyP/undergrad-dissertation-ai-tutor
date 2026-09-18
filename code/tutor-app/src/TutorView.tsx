import { useRef, useState, useCallback } from 'react'
import VideoPlayer from './VideoPlayer'
import type { VideoPlayerHandle } from './VideoPlayer'
import QuestionOverlay from './QuestionOverlay'
import Chat from './Chat'
import { useTutorController } from './hooks/useTutorController'
import { useInterpolatedQuestions } from './hooks/useInterpolatedQuestions'
import { useInterpolatedQuestionFlow } from './hooks/useInterpolatedQuestionFlow'
import { levelLabels } from './lib/tutorUtils'

export interface InterpolatedAttemptPayload {
  question_id: number
  question_text: string
  topic: string
  correct: boolean
  attempt_count: number
  used_hint: boolean
  rewatched: boolean
  scaffold_score_after?: number
}

export interface ChatEntry {
  sender: 'user' | 'tutor'
  text: string
  sent_at: string
}

interface TutorViewProps {
  participantId: string
  videoSrc: string
  subtitleSrc?: string
  topic: 'liberalism' | 'rep-democracy'
  model?: string
  initialScore: number
  onComplete: (finalScaffoldScore: number, chatEntries: ChatEntry[]) => void
  onInterpolatedAttempt: (payload: InterpolatedAttemptPayload) => void
}

function TutorView({ participantId, videoSrc, subtitleSrc, topic, model, initialScore, onComplete, onInterpolatedAttempt }: TutorViewProps) {
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)

  const playerRef = useRef<VideoPlayerHandle>(null)
  const pauseVideo = () => playerRef.current?.pause()
  const playVideo = () => playerRef.current?.play()
  const seekVideo = (time: number) => playerRef.current?.seekTo(time)

  const { questions, questionsLoaded } = useInterpolatedQuestions(topic)

  const controller = useTutorController({
    topic,
    model,
    initialScore,
    interpolatedQuestions: questions,
    currentTime,
    playVideo,
    seekVideo,
  })

  const flow = useInterpolatedQuestionFlow({
    questions,
    pauseVideo,
    onAnswer: (correct, attempts, selectedOption, question) => {
      controller.handleAnswer(correct, attempts, selectedOption, question)
      onInterpolatedAttempt({
        question_id: question.id,
        question_text: question.question,
        topic,
        correct,
        attempt_count: attempts,
        used_hint: false,
        rewatched: false,
        scaffold_score_after: controller.scaffoldScore,
      })
    },
    isBusy: () => !!(
      controller.pendingExplanation ||
      controller.consolidation ||
      controller.awaitingChoice ||
      controller.remediation
    ),
  })

  const showFinishedButton = duration > 0 && currentTime >= duration - 30

  const buildChatEntries = useCallback((): ChatEntry[] => {
    return controller.messages.map(m => {
      const sent_at = controller.getMessageTimestamp(m.id)
      if (m.type === 'text') {
        return { sender: m.sender as 'user' | 'tutor', text: m.text, sent_at }
      }
      if (m.type === 'consolidation') {
        const optionLines = m.data.options.map((o, i) => {
          const letter = String.fromCharCode(65 + i)
          const correct = i === m.data.correctIndex ? ' ✓' : ''
          return `  ${letter}) ${o}${correct}`
        })
        const text = `[MCQ] ${m.data.question}\n${optionLines.join('\n')}`
        return { sender: 'tutor' as const, text, sent_at }
      }
      if (m.type === 'choice') {
        return { sender: 'tutor' as const, text: `[CHOICE] ${m.text}`, sent_at }
      }
      return { sender: 'tutor' as const, text: `[INTERVENTION] ${m.text}`, sent_at }
    })
  }, [controller.messages, controller.getMessageTimestamp])

  if (!questionsLoaded) {
    return <main className="layout"><p style={{ padding: '1rem' }}>Loading…</p></main>
  }

  return (
    <main className="layout">
      <section className="video-panel" aria-label="Video and questions">
        <div className="participant-id-badge" aria-label={`Participant ID: ${participantId}`}>
          ID: <strong>{participantId}</strong>
        </div>
        <div className="scaffold-indicator" aria-label={`Current scaffolding level: ${levelLabels[controller.currentLevel]}`}>
          <span className="scaffold-label">Scaffolding:</span>
          <span className={`scaffold-level scaffold-level-${controller.currentLevel}`}>
            L{controller.currentLevel} — {levelLabels[controller.currentLevel]}
          </span>
          <span className="scaffold-score">(score: {controller.scaffoldScore.toFixed(2)})</span>
        </div>
        <div className="video-wrapper">
          <VideoPlayer
            ref={playerRef}
            src={videoSrc}
            subtitleSrc={subtitleSrc}
            markers={flow.markers}
            onTimeUpdate={(time) => { setCurrentTime(time); flow.handleTimeUpdate(time) }}
            onDurationChange={setDuration}
            onEnded={() => onComplete(controller.scaffoldScore, buildChatEntries())}
          />
          {flow.activeQuestion && (
            <QuestionOverlay
              question={flow.activeQuestion}
              onAnswer={flow.handleAnswer}
              onHint={() => controller.handleHint(flow.activeQuestion!)}
              onRewatch={() => {
                const { rewatchStart } = flow.activeQuestion!
                flow.dismissActiveQuestion()
                playerRef.current?.seekTo(rewatchStart)
                playerRef.current?.play()
              }}
              onReword={async () => {
                const original = flow.activeQuestion!
                const reworded = await controller.handleReword(original)
                if (reworded) {
                  flow.updateActiveQuestion(reworded)
                  controller.addTextMessage('tutor', `I've replaced the question with a reworded version in the overlay.\n\nHere is the original phrasing if it helps:\n"${original.question}"`)
                } else {
                  controller.addTextMessage('tutor', "I wasn't able to rephrase that question right now — the original still applies.")
                }
              }}
            />
          )}
        </div>
        {showFinishedButton && (
          <button className="finished-button" onClick={() => onComplete(controller.scaffoldScore, buildChatEntries())}>
            I'm finished — continue
          </button>
        )}
      </section>

      <aside className="chat-panel" aria-label="AI tutor chat">
        <Chat
          messages={controller.messages}
          onSend={controller.handleSend}
          onConsolidationAnswer={(messageId, selectedIndex) => {
            // Route to the right handler based on which flow is active.
            // Remediation MCQs (easy + post-intervention) and consolidation/mastery/discussion_check
            // MCQs all render as ConsolidationCard, so we dispatch here.
            const step = controller.remediation?.step
            if (step === 'easy_mcq') {
              controller.handleRemediationAnswer(selectedIndex)
            } else if (step === 'post_intervention_mcq') {
              controller.handlePostInterventionAnswer(selectedIndex)
            } else {
              controller.handleConsolidationAnswer(messageId, selectedIndex)
            }
          }}
          onChoice={controller.handleChoice}
          onIntervention={controller.handleInterventionChoice}
          disabled={controller.isTutorLoading}
          onSeekVideo={(time) => {
            playerRef.current?.seekTo(time)
            playerRef.current?.play()
          }}
        />
      </aside>
    </main>
  )
}

export default TutorView
