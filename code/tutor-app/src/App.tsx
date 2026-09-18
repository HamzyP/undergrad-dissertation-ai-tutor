import { useEffect, useRef, useState } from 'react'
import { Routes, Route } from 'react-router-dom'
import WelcomeView from './WelcomeView'
import QuizView from './QuizView'
import TutorView from './TutorView'
import VideoOnlyView from './VideoOnlyView'
import PostQuizView from './PostQuizView'
import AdminView from './AdminView'
import SessionSummaryView from './SessionSummaryView'

function generateParticipantId(): string {
  return String(Math.floor(10000 + Math.random() * 90000))
}

type Theme = 'light' | 'dark' | 'high-contrast' | 'cb-deuteranopia' | 'cb-protanopia' | 'cb-tritanopia' | 'cb-achromatopsia'

const CB_THEMES: { value: Theme; label: string; desc: string }[] = [
  { value: 'cb-deuteranopia',   label: 'Deuteranopia',   desc: 'Red-green (most common)' },
  { value: 'cb-protanopia',     label: 'Protanopia',     desc: 'Red-green (reds darkened)' },
  { value: 'cb-tritanopia',     label: 'Tritanopia',     desc: 'Blue-yellow confusion' },
  { value: 'cb-achromatopsia',  label: 'Achromatopsia',  desc: 'Full colour blindness' },
]

type Group = 'A' | 'B' | 'C' | 'D'
type Topic = 'liberalism' | 'rep-democracy'
type Phase = 'welcome' | 'pre-quiz' | 'video-1' | 'video-2' | 'post-quiz' | 'session-summary' | 'done'

interface TopicScore { topic: Topic; correct: number; total: number }

interface VideoConfig {
  topic: Topic
  src: string
  subtitleSrc: string
  withTutor: boolean
}

// Chat messages captured from TutorView for persistence
interface ChatEntry { sender: 'user' | 'tutor'; text: string; sent_at: string }

function getVideoSequence(group: Group): [VideoConfig, VideoConfig] {
  const liberalism = { topic: 'liberalism' as const, src: '/videos/liberalism.mp4', subtitleSrc: '/videos/liberalism.vtt' }
  const repDem = { topic: 'rep-democracy' as const, src: '/videos/rep-democracy.mp4', subtitleSrc: '/videos/rep-democracy.vtt' }

  if (group === 'A') return [{ ...liberalism, withTutor: true  }, { ...repDem,    withTutor: false }]
  if (group === 'B') return [{ ...liberalism, withTutor: false }, { ...repDem,    withTutor: true  }]
  if (group === 'C') return [{ ...repDem,    withTutor: true  }, { ...liberalism, withTutor: false }]
  return                     [{ ...repDem,    withTutor: false }, { ...liberalism, withTutor: true  }]
}

function ParticipantApp() {
  const [theme, setTheme] = useState<Theme>('dark')
  const [cbOpen, setCbOpen] = useState(false)
  const cbRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (cbRef.current && !cbRef.current.contains(e.target as Node)) setCbOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  const [participantId] = useState<string>(() => generateParticipantId())
  const [group, setGroup] = useState<Group | null>(null)
  const [selectedModel, setSelectedModel] = useState<string | null>(null)
  const [phase, setPhase] = useState<Phase>('welcome')

  // Per-topic scores — indexed by topic key
  const [preScores, setPreScores] = useState<TopicScore[]>([])
  const [postScores, setPostScores] = useState<TopicScore[]>([])
  const [finalScaffoldScore, setFinalScaffoldScore] = useState<number | null>(null)
  const chatHistoryRef = useRef<ChatEntry[]>([])

  const videoSequence = group ? getVideoSequence(group) : null
  const topicOrder = videoSequence ? [videoSequence[0].topic, videoSequence[1].topic] as [Topic, Topic] : ['liberalism', 'rep-democracy'] as [Topic, Topic]

  const getInitialScaffoldScore = (topic: Topic) => {
    const preScore = preScores.find(s => s.topic === topic)
    return preScore
      ? ((preScore.correct / preScore.total) * 6) - 2
      : 0
  }

  const recordInterpolatedAttempt = (payload: object) => {
    fetch(`http://127.0.0.1:8000/api/participants/${participantId}/attempt/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).catch(() => {})
  }

  const finaliseSession = (scores: TopicScore[], scaffold: number | null) => {
    const byTopic = (topic: Topic, which: 'pre' | 'post') => {
      const arr = which === 'pre' ? preScores : scores
      return arr.find(s => s.topic === topic)
    }
    const lib_pre  = byTopic('liberalism',    'pre')
    const rep_pre  = byTopic('rep-democracy', 'pre')
    const lib_post = byTopic('liberalism',    'post')
    const rep_post = byTopic('rep-democracy', 'post')

    fetch(`http://127.0.0.1:8000/api/participants/${participantId}/finalise/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        lib_pre_correct:  lib_pre?.correct  ?? null,
        lib_pre_total:    lib_pre?.total    ?? null,
        lib_post_correct: lib_post?.correct ?? null,
        lib_post_total:   lib_post?.total   ?? null,
        rep_pre_correct:  rep_pre?.correct  ?? null,
        rep_pre_total:    rep_pre?.total    ?? null,
        rep_post_correct: rep_post?.correct ?? null,
        rep_post_total:   rep_post?.total   ?? null,
        final_scaffold_score: scaffold,
        chat_messages: chatHistoryRef.current,
      }),
    }).catch(() => {})
  }

  const handleStart = (
    selectedGroup: Group,
    model: string,
    consent: {
      info: boolean
      age: boolean
      stem: boolean
      consentForm: boolean
      postSessionQuestionnaire: boolean
    },
  ) => {
    setGroup(selectedGroup)
    setSelectedModel(model)
    fetch('http://127.0.0.1:8000/api/participants/create/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ participant_id: participantId, group: selectedGroup }),
    })
      .then(() => fetch(`http://127.0.0.1:8000/api/participants/${participantId}/consent/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          info_sheet: consent.info,
          over_18: consent.age,
          stem_student: consent.stem,
          consent_form: consent.consentForm,
          post_session_questionnaire: consent.postSessionQuestionnaire,
        }),
      }))
      .catch(() => {})
    setPhase('pre-quiz')
  }

  const renderPhase = () => {
    if (phase === 'welcome') {
      return <WelcomeView participantId={participantId} onStart={handleStart} />
    }

    if (phase === 'pre-quiz') {
      return (
        <QuizView
          topicOrder={topicOrder}
          quizType="pre"
          onComplete={(scores) => {
            setPreScores(scores)
            setPhase('video-1')
          }}
        />
      )
    }

    if (phase === 'video-1' && videoSequence) {
      const v = videoSequence[0]
      return v.withTutor ? (
        <TutorView
          participantId={participantId}
          videoSrc={v.src} subtitleSrc={v.subtitleSrc} topic={v.topic}
          model={selectedModel ?? undefined} initialScore={getInitialScaffoldScore(v.topic)}
          onComplete={(score, chatEntries) => {
            setFinalScaffoldScore(score)
            chatHistoryRef.current = [...chatHistoryRef.current, ...chatEntries]
            setPhase('video-2')
          }}
          onInterpolatedAttempt={recordInterpolatedAttempt}
        />
      ) : (
        <VideoOnlyView participantId={participantId} videoSrc={v.src} subtitleSrc={v.subtitleSrc} onComplete={() => setPhase('video-2')} />
      )
    }

    if (phase === 'video-2' && videoSequence) {
      const v = videoSequence[1]
      return v.withTutor ? (
        <TutorView
          participantId={participantId}
          videoSrc={v.src} subtitleSrc={v.subtitleSrc} topic={v.topic}
          model={selectedModel ?? undefined} initialScore={getInitialScaffoldScore(v.topic)}
          onComplete={(score, chatEntries) => {
            setFinalScaffoldScore(score)
            chatHistoryRef.current = [...chatHistoryRef.current, ...chatEntries]
            setPhase('post-quiz')
          }}
          onInterpolatedAttempt={recordInterpolatedAttempt}
        />
      ) : (
        <VideoOnlyView participantId={participantId} videoSrc={v.src} subtitleSrc={v.subtitleSrc} onComplete={() => setPhase('post-quiz')} />
      )
    }

    if (phase === 'post-quiz') {
      return (
        <PostQuizView
          topicOrder={topicOrder}
          onComplete={(scores) => {
            setPostScores(scores)
            finaliseSession(scores, finalScaffoldScore)
            setPhase('session-summary')
          }}
        />
      )
    }

    if (phase === 'session-summary') {
      return (
        <SessionSummaryView
          topicOrder={topicOrder}
          preScores={preScores}
          postScores={postScores}
          onContinue={() => setPhase('done')}
        />
      )
    }

    if (phase === 'done') {
      return (
        <main className="quiz-view quiz-view--done">
          <h2>Session complete.</h2>
          <p>Thank you for participating.</p>
          <div className="participant-id-banner" style={{ marginTop: '1rem' }}>
            <span className="participant-id-label">Your Participant ID</span>
            <span className="participant-id-value">{participantId}</span>
            <p className="participant-id-hint">Please let the researcher know you have finished.</p>
          </div>
          <section className="done-questionnaire" aria-label="Optional post-session questionnaire">
            <p>Thank you for taking part. Please fill out this optional questionnaire to help us improve the tutor.</p>
            <a
              className="start-button questionnaire-link"
              href="https://forms.office.com/e/DEKACajZ59"
              target="_blank"
              rel="noopener noreferrer"
            >
              Open questionnaire
            </a>
          </section>
        </main>
      )
    }

    return null
  }

  const isCb = theme.startsWith('cb-')

  return (
    <div className={`app ${theme}`}>
      <nav className="theme-switcher" aria-label="Display mode">
        <button className={theme === 'light' ? 'active' : ''} onClick={() => { setTheme('light'); setCbOpen(false) }}>Light</button>
        <button className={theme === 'dark' ? 'active' : ''} onClick={() => { setTheme('dark'); setCbOpen(false) }}>Dark</button>
        <button className={theme === 'high-contrast' ? 'active' : ''} onClick={() => { setTheme('high-contrast'); setCbOpen(false) }}>High Contrast</button>
        <div className="cb-dropdown" ref={cbRef}>
          <button
            className={isCb ? 'active' : ''}
            onClick={() => setCbOpen(o => !o)}
            aria-haspopup="listbox"
            aria-expanded={cbOpen}
          >
            {isCb ? CB_THEMES.find(t => t.value === theme)!.label : 'Colourblind'} ▾
          </button>
          {cbOpen && (
            <ul className="cb-dropdown__menu" role="listbox">
              {CB_THEMES.map(t => (
                <li
                  key={t.value}
                  role="option"
                  aria-selected={theme === t.value}
                  className={theme === t.value ? 'cb-dropdown__item cb-dropdown__item--active' : 'cb-dropdown__item'}
                  onClick={() => { setTheme(t.value); setCbOpen(false) }}
                >
                  <span className="cb-dropdown__label">{t.label}</span>
                  <span className="cb-dropdown__desc">{t.desc}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </nav>
      {renderPhase()}
    </div>
  )
}

function App() {
  return (
    <Routes>
      <Route path="/admin" element={<AdminView />} />
      <Route path="/*" element={<ParticipantApp />} />
    </Routes>
  )
}

export default App
