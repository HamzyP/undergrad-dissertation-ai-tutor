import { Fragment, useEffect, useState } from 'react'

interface InterpolatedAttempt {
  question_id: number
  question_text: string
  topic: string
  correct: boolean
  attempt_count: number
  used_hint: boolean
  rewatched: boolean
  scaffold_score_after: number | null
  answered_at: string
}

interface ChatMessage {
  sender: 'user' | 'tutor'
  text: string
  sent_at: string
}

interface Session {
  participant_id: string
  group: string
  tutor_topic: string
  lib_pre_correct: number | null
  lib_pre_total: number | null
  lib_post_correct: number | null
  lib_post_total: number | null
  rep_pre_correct: number | null
  rep_pre_total: number | null
  rep_post_correct: number | null
  rep_post_total: number | null
  final_scaffold_score: number | null
  completed: boolean
  started_at: string
  completed_at: string | null
  interpolated_attempts: InterpolatedAttempt[]
  chat_messages: ChatMessage[]
}

type Topic = 'liberalism' | 'rep-democracy'
type Score = { correct: number; total: number }

const CORRECT_MARK = '\u2713'

function pct(correct: number | null, total: number | null): string {
  if (correct === null || total === null || total === 0) return '-'
  return `${Math.round((correct / total) * 100)}%`
}

function topicLabel(topic: Topic): string {
  return topic === 'liberalism' ? 'Liberalism' : 'Rep Democracy'
}

function aiTopic(session: Session): Topic {
  return session.tutor_topic === 'rep-democracy' ? 'rep-democracy' : 'liberalism'
}

function nonAiTopic(session: Session): Topic {
  return aiTopic(session) === 'liberalism' ? 'rep-democracy' : 'liberalism'
}

function topicScore(session: Session, topic: Topic, phase: 'pre' | 'post'): Score | null {
  if (topic === 'liberalism') {
    const correct = phase === 'pre' ? session.lib_pre_correct : session.lib_post_correct
    const total = phase === 'pre' ? session.lib_pre_total : session.lib_post_total
    return correct !== null && total !== null && total > 0 ? { correct, total } : null
  }

  const correct = phase === 'pre' ? session.rep_pre_correct : session.rep_post_correct
  const total = phase === 'pre' ? session.rep_pre_total : session.rep_post_total
  return correct !== null && total !== null && total > 0 ? { correct, total } : null
}

function scoreDisplay(score: Score | null): string {
  if (!score) return '-'
  return `${score.correct}/${score.total} (${pct(score.correct, score.total)})`
}

function gainDisplay(pre: Score | null, post: Score | null): string {
  if (!pre || !post) return '-'
  const gain = Math.round((post.correct / post.total - pre.correct / pre.total) * 100)
  return gain >= 0 ? `+${gain}%` : `${gain}%`
}

function gainValue(pre: Score | null, post: Score | null): number | null {
  if (!pre || !post) return null
  return Math.round((post.correct / post.total - pre.correct / pre.total) * 100)
}

function gainDiffDisplay(videoPre: Score | null, videoPost: Score | null, aiPre: Score | null, aiPost: Score | null): string {
  const videoGain = gainValue(videoPre, videoPost)
  const aiGain = gainValue(aiPre, aiPost)
  if (videoGain === null || aiGain === null) return '-'
  const diff = aiGain - videoGain
  return diff >= 0 ? `+${diff}%` : `${diff}%`
}

function gainClassName(value: string): string {
  if (value.startsWith('+')) return 'participants-gain participants-gain--positive'
  if (value.startsWith('-') && value !== '-') return 'participants-gain participants-gain--negative'
  return 'participants-gain'
}

function SessionStats({ s }: { s: Session }) {
  const ai = aiTopic(s)
  const video = nonAiTopic(s)
  const videoPre = topicScore(s, video, 'pre')
  const videoPost = topicScore(s, video, 'post')
  const aiPre = topicScore(s, ai, 'pre')
  const aiPost = topicScore(s, ai, 'post')
  const videoGain = gainDisplay(videoPre, videoPost)
  const aiGain = gainDisplay(aiPre, aiPost)
  const gainDiff = gainDiffDisplay(videoPre, videoPost, aiPre, aiPost)

  return (
    <div className="chat-viewer-stats">
      <div className="chat-viewer-stat">
        <span className="chat-viewer-stat-label">ID</span>
        <span className="chat-viewer-stat-value"><strong>{s.participant_id}</strong></span>
      </div>
      <div className="chat-viewer-stat">
        <span className="chat-viewer-stat-label">Group</span>
        <span className="chat-viewer-stat-value">{s.group}</span>
      </div>
      <div className="chat-viewer-stat">
        <span className="chat-viewer-stat-label">AI Topic</span>
        <span className="chat-viewer-stat-value">{topicLabel(ai)}</span>
      </div>
      <div className="chat-viewer-stat">
        <span className="chat-viewer-stat-label">Video Topic</span>
        <span className="chat-viewer-stat-value">{topicLabel(video)}</span>
      </div>
      <div className="chat-viewer-stat">
        <span className="chat-viewer-stat-label">Video Pre</span>
        <span className="chat-viewer-stat-value">{scoreDisplay(videoPre)}</span>
      </div>
      <div className="chat-viewer-stat">
        <span className="chat-viewer-stat-label">Video Post</span>
        <span className="chat-viewer-stat-value">{scoreDisplay(videoPost)}</span>
      </div>
      <div className="chat-viewer-stat">
        <span className="chat-viewer-stat-label">Video Gain</span>
        <span className={`chat-viewer-stat-value ${gainClassName(videoGain)}`}>{videoGain}</span>
      </div>
      <div className="chat-viewer-stat">
        <span className="chat-viewer-stat-label">AI Pre</span>
        <span className="chat-viewer-stat-value">{scoreDisplay(aiPre)}</span>
      </div>
      <div className="chat-viewer-stat">
        <span className="chat-viewer-stat-label">AI Post</span>
        <span className="chat-viewer-stat-value">{scoreDisplay(aiPost)}</span>
      </div>
      <div className="chat-viewer-stat">
        <span className="chat-viewer-stat-label">AI Gain</span>
        <span className={`chat-viewer-stat-value ${gainClassName(aiGain)}`}>{aiGain}</span>
      </div>
      <div className="chat-viewer-stat">
        <span className="chat-viewer-stat-label">Gain Diff</span>
        <span className={`chat-viewer-stat-value ${gainClassName(gainDiff)}`}>{gainDiff}</span>
      </div>
      <div className="chat-viewer-stat">
        <span className="chat-viewer-stat-label">Scaffold</span>
        <span className="chat-viewer-stat-value">{s.final_scaffold_score !== null ? s.final_scaffold_score.toFixed(2) : '-'}</span>
      </div>
      <div className="chat-viewer-stat">
        <span className="chat-viewer-stat-label">Status</span>
        <span className={`participants-status ${s.completed ? 'participants-status--complete' : 'participants-status--incomplete'}`}>
          {s.completed ? 'Complete' : 'In progress'}
        </span>
      </div>
      <div className="chat-viewer-stat">
        <span className="chat-viewer-stat-label">Started</span>
        <span className="chat-viewer-stat-value">{new Date(s.started_at).toLocaleString()}</span>
      </div>
    </div>
  )
}

function ChatBubble({ msg }: { msg: ChatMessage }) {
  const isMcq = msg.sender === 'tutor' && msg.text.startsWith('[MCQ] ')
  const isMcqAnswer = msg.sender === 'user' && msg.text.startsWith('[MCQ ANSWER] ')
  const isChoice = msg.sender === 'tutor' && msg.text.startsWith('[CHOICE] ')
  const isIntervention = msg.sender === 'tutor' && msg.text.startsWith('[INTERVENTION] ')

  if (isMcq) {
    const body = msg.text.slice('[MCQ] '.length)
    const [question, ...optionLines] = body.split('\n')
    return (
      <div className="chat-message chat-message-tutor chat-viewer-mcq">
        <span className="chat-sender">In-chat MCQ</span>
        <p className="chat-viewer-mcq-question">{question}</p>
        <ul className="chat-viewer-mcq-options">
          {optionLines.map((line, i) => (
            <li key={i} className={line.endsWith(` ${CORRECT_MARK}`) ? 'chat-viewer-mcq-correct' : ''}>{line}</li>
          ))}
        </ul>
        <span className="chat-viewer-time">{new Date(msg.sent_at).toLocaleTimeString()}</span>
      </div>
    )
  }

  if (isMcqAnswer) {
    const body = msg.text.slice('[MCQ ANSWER] '.length)
    const correct = body.endsWith(` ${CORRECT_MARK}`)
    return (
      <div className={`chat-message chat-message-user chat-viewer-mcq-answer ${correct ? 'chat-viewer-mcq-answer--correct' : 'chat-viewer-mcq-answer--incorrect'}`}>
        <span className="chat-sender">Participant answered</span>
        <span className="chat-text">{body}</span>
        <span className="chat-viewer-time">{new Date(msg.sent_at).toLocaleTimeString()}</span>
      </div>
    )
  }

  const label = isChoice ? '[CHOICE] ' : isIntervention ? '[INTERVENTION] ' : null
  const displayText = label ? msg.text.slice(label.length) : msg.text
  const tag = isChoice ? 'Choice' : isIntervention ? 'Intervention' : null

  return (
    <div className={`chat-message ${msg.sender === 'user' ? 'chat-message-user' : 'chat-message-tutor'}`}>
      <span className="chat-sender">
        {tag ?? (msg.sender === 'user' ? 'Participant' : 'Tutor')}
      </span>
      <span className="chat-text">{displayText}</span>
      <span className="chat-viewer-time">{new Date(msg.sent_at).toLocaleTimeString()}</span>
    </div>
  )
}

function ChatViewer({ session, onBack }: { session: Session; onBack: () => void }) {
  return (
    <div className="chat-viewer">
      <div className="chat-viewer-header">
        <button className="admin-back-btn" onClick={onBack}>{'<-'} Back</button>
        <h2 className="chat-viewer-title">Chat - Participant {session.participant_id}</h2>
      </div>
      <SessionStats s={session} />
      {session.chat_messages.length === 0 ? (
        <p className="admin-status">No chat messages recorded for this session.</p>
      ) : (
        <div className="chat-viewer-messages">
          {session.chat_messages.map((msg, i) => (
            <ChatBubble key={i} msg={msg} />
          ))}
        </div>
      )}
    </div>
  )
}

export default function ParticipantsTab() {
  const [sessions, setSessions] = useState<Session[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [viewingChat, setViewingChat] = useState<Session | null>(null)

  useEffect(() => {
    fetch('http://127.0.0.1:8000/api/participants/')
      .then(r => r.json())
      .then(data => { setSessions(data); setLoading(false) })
      .catch(() => { setError('Failed to load participants.'); setLoading(false) })
  }, [])

  const downloadCsv = (table: 'sessions' | 'attempts' | 'chat' | 'consent') => {
    window.open(`http://127.0.0.1:8000/api/participants/export/?table=${table}`, '_blank')
  }

  const handleDelete = async (participantId: string) => {
    setDeleting(participantId)
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/participants/${participantId}/`, { method: 'DELETE' })
      if (res.ok) {
        setSessions(prev => prev.filter(s => s.participant_id !== participantId))
        if (viewingChat?.participant_id === participantId) setViewingChat(null)
      }
    } finally {
      setDeleting(null)
      setConfirmDelete(null)
    }
  }

  if (loading) return <p className="admin-status">Loading participants...</p>
  if (error) return <p className="admin-status admin-status--error">{error}</p>

  if (viewingChat) {
    return <ChatViewer session={viewingChat} onBack={() => setViewingChat(null)} />
  }

  const completedCount = sessions.filter(s => s.completed).length

  return (
    <div className="participants-tab">
      <div className="participants-header">
        <div className="participants-summary">
          <span><strong>{sessions.length}</strong> total sessions</span>
          <span><strong>{completedCount}</strong> completed</span>
        </div>
        <div className="participants-export-buttons">
          <button className="admin-btn" onClick={() => downloadCsv('sessions')}>
            Export Sessions CSV
          </button>
          <button className="admin-btn" onClick={() => downloadCsv('attempts')}>
            Export Attempts CSV
          </button>
          <button className="admin-btn" onClick={() => downloadCsv('chat')}>
            Export Chat CSV
          </button>
          <button className="admin-btn" onClick={() => downloadCsv('consent')}>
            Export Consent CSV
          </button>
        </div>
      </div>

      {sessions.length === 0 ? (
        <p className="admin-status">No sessions recorded yet.</p>
      ) : (
        <div className="participants-table-wrap">
          <table className="participants-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Group</th>
                <th>AI Topic</th>
                <th>Video Pre Score</th>
                <th>Video Post Score</th>
                <th>Video Gain</th>
                <th>AI Pre Score</th>
                <th>AI Post Score</th>
                <th>AI Gain</th>
                <th>Gain Diff</th>
                <th>Chat</th>
                <th>Status</th>
                <th>Started</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {sessions.map(s => {
                const ai = aiTopic(s)
                const video = nonAiTopic(s)
                const videoPre = topicScore(s, video, 'pre')
                const videoPost = topicScore(s, video, 'post')
                const aiPre = topicScore(s, ai, 'pre')
                const aiPost = topicScore(s, ai, 'post')
                const videoGain = gainDisplay(videoPre, videoPost)
                const aiGain = gainDisplay(aiPre, aiPost)
                const gainDiff = gainDiffDisplay(videoPre, videoPost, aiPre, aiPost)

                return (
                  <Fragment key={s.participant_id}>
                    <tr
                      className="participants-row"
                    >
                      <td><strong>{s.participant_id}</strong></td>
                      <td>{s.group}</td>
                      <td>{topicLabel(ai)}</td>
                      <td className="participants-score">{scoreDisplay(videoPre)}</td>
                      <td className="participants-score">{scoreDisplay(videoPost)}</td>
                      <td className={`participants-score ${gainClassName(videoGain)}`}>{videoGain}</td>
                      <td className="participants-score">{scoreDisplay(aiPre)}</td>
                      <td className="participants-score">{scoreDisplay(aiPost)}</td>
                      <td className={`participants-score ${gainClassName(aiGain)}`}>{aiGain}</td>
                      <td className={`participants-score ${gainClassName(gainDiff)}`}>{gainDiff}</td>
                      <td onClick={e => e.stopPropagation()}>
                        {s.chat_messages.length > 0 ? (
                          <button
                            className="participants-chat-btn"
                            onClick={() => setViewingChat(s)}
                          >
                            {s.chat_messages.length} msgs
                          </button>
                        ) : '-'}
                      </td>
                      <td>
                        <span className={`participants-status ${s.completed ? 'participants-status--complete' : 'participants-status--incomplete'}`}>
                          {s.completed ? 'Complete' : 'In progress'}
                        </span>
                      </td>
                      <td>{new Date(s.started_at).toLocaleString()}</td>
                      <td onClick={e => e.stopPropagation()}>
                        {confirmDelete === s.participant_id ? (
                          <span className="participants-delete-confirm">
                            Delete?{' '}
                            <button
                              className="participants-delete-confirm-btn"
                              onClick={() => handleDelete(s.participant_id)}
                              disabled={deleting === s.participant_id}
                            >
                              {deleting === s.participant_id ? '...' : 'Yes'}
                            </button>
                            {' / '}
                            <button
                              className="participants-delete-cancel-btn"
                              onClick={() => setConfirmDelete(null)}
                            >
                              No
                            </button>
                          </span>
                        ) : (
                          <button
                            className="participants-delete-btn"
                            onClick={() => setConfirmDelete(s.participant_id)}
                            aria-label={`Delete participant ${s.participant_id}`}
                          >
                            Delete
                          </button>
                        )}
                      </td>
                    </tr>
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
