import { useEffect, useState, useCallback } from 'react'

const API = 'http://127.0.0.1:8000/api'

type Topic = 'liberalism' | 'rep-democracy'
type QuizType = 'pre' | 'interpolated'

interface Citation {
  source_type: string
  source_id: string
  title: string
  url: string
  location: string
  start_time?: number | null
}

interface Question {
  id: number
  topic: Topic
  quiz_type: QuizType
  order_index: number
  question_text: string
  option_a: string
  option_b: string
  option_c: string
  option_d: string
  correct_index: number
  timestamp: number | null
  rewatch_start: number | null
  transcript_excerpt: string | null
  citations: Citation[]
}

interface GenerateResult {
  topic: Topic
  quiz_type: 'pre' | 'interpolated'
  created: number
  errors: number
  latency_ms: number
  accepted_count?: number
  rejection_summary?: Record<string, number>
  error?: string
}

const TOPICS: { value: Topic; label: string }[] = [
  { value: 'liberalism', label: 'Liberalism' },
  { value: 'rep-democracy', label: 'Representative Democracy' },
]

const QUIZ_TYPES: { value: QuizType; label: string }[] = [
  { value: 'pre', label: 'Pre/Post' },
  { value: 'interpolated', label: 'Interpolated' },
]

const ALL_COMBOS: { topic: Topic; quiz_type: QuizType }[] = TOPICS.flatMap(t =>
  QUIZ_TYPES.map(qt => ({ topic: t.value, quiz_type: qt.value }))
)

const CORRECT_LABELS = ['A', 'B', 'C', 'D']

const DEFAULT_COUNT_PRE_POST = 7
const DEFAULT_COUNT_INTERPOLATED = 3

function formatRejectionSummary(rejectionSummary: Record<string, number> | undefined): string {
  if (!rejectionSummary) return ''

  const parts: string[] = []
  for (const [reason, count] of Object.entries(rejectionSummary)) {
    parts.push(`${count}× ${reason}`)
  }
  return parts.join(' | ')
}

function formatGenerateError(data: any, statusCode: number): string {
  const base = data?.error || `HTTP ${statusCode}`
  const details: string[] = []

  if (typeof data?.accepted_count === 'number') {
    details.push(`Accepted drafts before failure: ${data.accepted_count}`)
  }

  const summaryText = formatRejectionSummary(data?.rejection_summary)
  if (summaryText) {
    details.push(`Rejects: ${summaryText}`)
  }

  if (details.length === 0) return base
  return `${base} ${details.join(' · ')}`
}

function citationHref(topic: Topic, citation: Citation): string | null {
  if (citation.url) return citation.url
  if (citation.source_type === 'transcript' && typeof citation.start_time === 'number') {
    // Transcript citations deep-link back into the local lecture video.
    return `/videos/${topic}.mp4#t=${Math.max(0, Math.floor(citation.start_time))}`
  }
  return null
}

function GroundingEvidence({ topic, citations }: { topic: Topic; citations: Citation[] }) {
  if (citations.length === 0) return null

  return (
    <div style={{ marginTop: '0.6rem' }}>
      <p className="admin-muted" style={{ fontSize: '0.78rem', marginBottom: '0.3rem' }}>
        Grounding evidence
      </p>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }}>
        {citations.map((citation, index) => {
          const labelParts = []
          if (citation.title) labelParts.push(citation.title)
          if (citation.location) labelParts.push(citation.location)
          const label = labelParts.join(' · ')
          const href = citationHref(topic, citation)
          return href ? (
            <a
              key={`${citation.source_type}-${citation.source_id}-${index}`}
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="admin-badge admin-badge--sep"
              style={{ textDecoration: 'none' }}
            >
              {label || citation.source_id}
            </a>
          ) : (
            <span
              key={`${citation.source_type}-${citation.source_id}-${index}`}
              className="admin-badge admin-badge--sep"
            >
              {label || citation.source_id}
            </span>
          )
        })}
      </div>
    </div>
  )
}

function formatTimestamp(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds))
  const minutes = Math.floor(total / 60)
  const remainder = total % 60
  return `${minutes}:${String(remainder).padStart(2, '0')}`
}

function QuestionExcerpt({ topic, question }: { topic: Topic; question: Question }) {
  if (!question.transcript_excerpt) return null

  const hasTiming = question.timestamp !== null || question.rewatch_start !== null
  const isInterpolated = question.quiz_type === 'interpolated'

  return (
    <div style={{ marginTop: '0.5rem' }}>
      {hasTiming && isInterpolated && (
        <p className="admin-muted" style={{ fontSize: '0.78rem' }}>
          {question.timestamp !== null && <>Timestamp: {question.timestamp}s</>}
          {question.timestamp !== null && question.rewatch_start !== null && ' · '}
          {question.rewatch_start !== null && <>Rewatch from: {question.rewatch_start}s</>}
          {question.timestamp !== null && (
            <>
              {' · '}
              <a
                href={`/videos/${topic}.mp4#t=${question.timestamp}`}
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: 'inherit', textDecoration: 'underline' }}
              >
                Watch at {question.timestamp}s ↗
              </a>
            </>
          )}
        </p>
      )}
      {hasTiming && !isInterpolated && (
        <p className="admin-muted" style={{ fontSize: '0.78rem' }}>
          Transcript grounding excerpt
          {question.rewatch_start !== null && question.timestamp !== null && (
            <>: {formatTimestamp(question.rewatch_start)}-{formatTimestamp(question.timestamp)}</>
          )}
        </p>
      )}
      <blockquote style={{
        margin: '0.4rem 0 0',
        padding: '0.4rem 0.6rem',
        borderLeft: '3px solid #555',
        fontSize: '0.78rem',
        color: '#aaa',
        fontStyle: 'italic',
        lineHeight: 1.5,
      }}>
        {question.transcript_excerpt}
      </blockquote>
    </div>
  )
}

async function generateOne(topic: Topic, quiz_type: QuizType, model: string | undefined, count: number): Promise<GenerateResult> {
  const r = await fetch(`${API}/questions/generate/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ topic, quiz_type, model, count }),
  })
  const data = await r.json()
  if (!r.ok) {
    return {
      topic,
      quiz_type,
      created: 0,
      errors: data.errors?.length ?? 0,
      latency_ms: data.latency_ms ?? 0,
      accepted_count: data.accepted_count,
      rejection_summary: data.rejection_summary,
      error: formatGenerateError(data, r.status),
    }
  }
  return {
    topic,
    quiz_type,
    created: data.created?.length ?? 0,
    errors: data.errors?.length ?? 0,
    latency_ms: data.latency_ms ?? 0,
  }
}

export default function QuestionsTab({ availableModels }: { availableModels: string[] }) {
  const [topic, setTopic] = useState<Topic>('liberalism')
  const [quizType, setQuizType] = useState<QuizType>('pre')
  const [questions, setQuestions] = useState<Question[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const [generateModel, setGenerateModel] = useState(availableModels[0] ?? '')
  const [generateCount, setGenerateCount] = useState<number>(DEFAULT_COUNT_PRE_POST)
  const [generating, setGenerating] = useState(false)
  const [generateError, setGenerateError] = useState('')
  const [generateInfo, setGenerateInfo] = useState('')

  // Generate-all progress
  const [generatingAll, setGeneratingAll] = useState(false)
  const [generateAllProgress, setGenerateAllProgress] = useState<GenerateResult[]>([])
  const [generateAllDone, setGenerateAllDone] = useState(false)

  const [editingId, setEditingId] = useState<number | null>(null)
  const [editDraft, setEditDraft] = useState<Partial<Question>>({})
  const [saving, setSaving] = useState(false)

  const fetchQuestions = useCallback(() => {
    setLoading(true)
    setError('')
    fetch(`${API}/questions/?topic=${topic}&quiz_type=${quizType}`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then(setQuestions)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [topic, quizType])

  useEffect(() => {
    fetchQuestions()
    setEditingId(null)
    setEditDraft({})
    setGenerateError('')
    setGenerateInfo('')
    setGenerateCount(quizType === 'interpolated' ? DEFAULT_COUNT_INTERPOLATED : DEFAULT_COUNT_PRE_POST)
  }, [fetchQuestions, quizType])

  // Keep model in sync if availableModels loads after mount
  useEffect(() => {
    if (!generateModel && availableModels.length > 0) {
      setGenerateModel(availableModels[0])
    }
  }, [availableModels, generateModel])

  const handleDelete = async (id: number) => {
    if (!confirm('Delete this question?')) return
    await fetch(`${API}/questions/${id}/`, { method: 'DELETE' })
    setQuestions(prev => prev.filter(q => q.id !== id))
  }

  const handleDeleteAll = async () => {
    if (!confirm('Delete ALL questions across every topic and quiz type? This cannot be undone.')) return
    const r = await fetch(`${API}/questions/`, { method: 'DELETE' })
    if (!r.ok) { alert(`Failed to delete all questions: HTTP ${r.status}`); return }
    setQuestions([])
  }

  const handleDeleteShown = async () => {
    if (!confirm(`Delete all questions for ${topicLabel(topic)} / ${typeLabel(quizType)}? This cannot be undone.`)) return
    const ids = questions.map(q => q.id)
    await Promise.all(ids.map(id => fetch(`${API}/questions/${id}/`, { method: 'DELETE' })))
    setQuestions([])
  }

  const startEdit = (q: Question) => { setEditingId(q.id); setEditDraft({ ...q }) }
  const cancelEdit = () => { setEditingId(null); setEditDraft({}) }

  const saveEdit = async () => {
    if (editingId === null) return
    setSaving(true)
    try {
      const r = await fetch(`${API}/questions/${editingId}/`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editDraft),
      })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const updated: Question = await r.json()
      setQuestions(prev => prev.map(q => (q.id === editingId ? updated : q)))
      setEditingId(null)
      setEditDraft({})
    } catch (e: unknown) {
      alert('Save failed: ' + (e instanceof Error ? e.message : String(e)))
    } finally {
      setSaving(false)
    }
  }

  const handleGenerate = async () => {
    setGenerating(true)
    setGenerateError('')
    setGenerateInfo('')
    const result = await generateOne(topic, quizType, generateModel || undefined, generateCount)
    if (result.error) {
      setGenerateError(result.error)
    } else {
      setGenerateInfo(
        `Generated ${result.created} question${result.created !== 1 ? 's' : ''}` +
        (result.errors > 0 ? ` (${result.errors} skipped)` : '') +
        `. Latency: ${result.latency_ms}ms`
      )
      fetchQuestions()
    }
    setGenerating(false)
  }

  const handleGenerateAll = async () => {
    if (!confirm(`Generate questions for every topic and quiz type (2 topics × 2 types = 4 sets)? Existing questions are preserved.`)) return
    setGeneratingAll(true)
    setGenerateAllProgress([])
    setGenerateAllDone(false)

    const results: GenerateResult[] = []
    for (const combo of ALL_COMBOS) {
      const comboCount = combo.quiz_type === 'interpolated' ? DEFAULT_COUNT_INTERPOLATED : DEFAULT_COUNT_PRE_POST
      const result = await generateOne(combo.topic, combo.quiz_type, generateModel || undefined, comboCount)
      results.push(result)
      setGenerateAllProgress([...results])
    }

    setGenerateAllDone(true)
    setGeneratingAll(false)
    fetchQuestions()
  }

  const topicLabel = (t: Topic) => TOPICS.find(x => x.value === t)?.label ?? t
  const typeLabel = (qt: QuizType) => QUIZ_TYPES.find(x => x.value === qt)?.label ?? qt

  return (
    <div className="admin-panels">

      {/* Selector row */}
      <section className="admin-panel">
        <div className="admin-toolbar">
          <div className="admin-toolbar-group">
            <label className="admin-label">Topic</label>
            <div className="admin-tab-group">
              {TOPICS.map(t => (
                <button key={t.value} className={`admin-tab ${topic === t.value ? 'admin-tab--active' : ''}`} onClick={() => setTopic(t.value)}>
                  {t.label}
                </button>
              ))}
            </div>
          </div>
          <div className="admin-toolbar-group">
            <label className="admin-label">Quiz type</label>
            <div className="admin-tab-group">
              {QUIZ_TYPES.map(qt => (
                <button key={qt.value} className={`admin-tab ${quizType === qt.value ? 'admin-tab--active' : ''}`} onClick={() => setQuizType(qt.value)}>
                  {qt.label}
                </button>
              ))}
            </div>
          </div>
          <div className="admin-toolbar-group" style={{ marginLeft: 'auto' }}>
            <label className="admin-label">Danger zone</label>
            <button className="admin-btn admin-btn--danger" onClick={handleDeleteAll}>
              Delete all questions
            </button>
          </div>
        </div>
      </section>

      {/* Generate panel */}
      <section className="admin-panel">
        <div className="admin-toolbar">
          {availableModels.length > 0 && (
            <div className="admin-toolbar-group">
              <label className="admin-label">Model</label>
              <select className="admin-select" value={generateModel} onChange={e => setGenerateModel(e.target.value)}>
                {availableModels.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
          )}
          <div className="admin-toolbar-group">
            <label className="admin-label">Count</label>
            <select className="admin-select" value={generateCount} onChange={e => setGenerateCount(Number(e.target.value))}>
              {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map(n => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
          </div>
          <div className="admin-toolbar-group" style={{ alignItems: 'flex-end' }}>
            <label className="admin-label">Generate</label>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button className="admin-btn admin-btn--primary" onClick={handleGenerate} disabled={generating || generatingAll}>
                {generating ? 'Generating…' : `${topicLabel(topic)} / ${typeLabel(quizType)}`}
              </button>
              <button className="admin-btn" onClick={handleGenerateAll} disabled={generating || generatingAll}>
                {generatingAll ? `(${generateAllProgress.length}/${ALL_COMBOS.length})…` : 'All topics & quiz types'}
              </button>
            </div>
          </div>
          {questions.length > 0 && (
            <div className="admin-toolbar-group" style={{ marginLeft: 'auto', alignItems: 'flex-end' }}>
              <label className="admin-label">Danger zone</label>
              <button className="admin-btn admin-btn--danger" onClick={handleDeleteShown} disabled={generating || generatingAll}>
                Delete {topicLabel(topic)} / {typeLabel(quizType)}
              </button>
            </div>
          )}
        </div>

        {generateError && <p className="admin-error" style={{ marginTop: '0.5rem' }}>Error: {generateError}</p>}
        {generateInfo && <p className="admin-success" style={{ marginTop: '0.5rem' }}>{generateInfo}</p>}

        {/* Generate-all progress log */}
        {(generatingAll || (generateAllDone && generateAllProgress.length > 0)) && (
          <div className="admin-generate-log">
            <p className="admin-label" style={{ marginBottom: '0.4rem' }}>
              {generatingAll ? 'Running…' : 'Complete'}
            </p>
            {generateAllProgress.map((r, i) => (
              <div key={i} className={`admin-generate-log-row ${r.error ? 'admin-generate-log-row--error' : 'admin-generate-log-row--ok'}`}>
                <span>{topicLabel(r.topic)} / {typeLabel(r.quiz_type)}</span>
                {r.error
                  ? <span>✗ {r.error}</span>
                  : <span>✓ {r.created} questions · {r.latency_ms}ms{r.errors > 0 ? ` · ${r.errors} skipped` : ''}</span>
                }
              </div>
            ))}
            {generatingAll && (
              <div className="admin-generate-log-row admin-generate-log-row--pending">
                <span>{topicLabel(ALL_COMBOS[generateAllProgress.length].topic)} / {typeLabel(ALL_COMBOS[generateAllProgress.length].quiz_type)}</span>
                <span>Generating…</span>
              </div>
            )}
          </div>
        )}
      </section>

      {/* Question list */}
      <section className="admin-panel">
        <h3>
          {topicLabel(topic)} — {typeLabel(quizType)}
          <span className="admin-count">{questions.length} question{questions.length !== 1 ? 's' : ''}</span>
        </h3>

        {loading && <p className="admin-muted">Loading…</p>}
        {error && <p className="admin-error">Error: {error}</p>}
        {!loading && questions.length === 0 && !error && (
          <p className="admin-muted">No questions yet. Use Generate above.</p>
        )}

        {questions.map(q => {
          const isEditing = editingId === q.id
          const d = isEditing ? editDraft : q

          return (
            <div key={q.id} className={`admin-question-card ${isEditing ? 'admin-question-card--editing' : ''}`}>
              <div className="admin-question-header">
                <span className="admin-question-num">#{q.order_index + 1}</span>
                {!isEditing && (
                  <div style={{ display: 'flex', gap: '0.5rem' }}>
                    <button className="admin-btn admin-btn--sm" onClick={() => startEdit(q)}>Edit</button>
                    <button className="admin-btn admin-btn--sm admin-btn--danger" onClick={() => handleDelete(q.id)}>Delete</button>
                  </div>
                )}
              </div>

              {isEditing ? (
                <div className="admin-edit-form">
                  <label className="admin-label">Question</label>
                  <textarea className="admin-textarea" rows={2} value={d.question_text ?? ''} onChange={e => setEditDraft(p => ({ ...p, question_text: e.target.value }))} />
                  {(['option_a', 'option_b', 'option_c', 'option_d'] as const).map((key, i) => (
                    <div key={key} style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                      <span className="admin-option-label">{CORRECT_LABELS[i]}</span>
                      <input className="admin-input" style={{ flex: 1 }} value={(d[key] as string) ?? ''} onChange={e => setEditDraft(p => ({ ...p, [key]: e.target.value }))} />
                    </div>
                  ))}
                  <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                    <label className="admin-label">Correct answer</label>
                    <select className="admin-select" value={d.correct_index ?? 0} onChange={e => setEditDraft(p => ({ ...p, correct_index: Number(e.target.value) }))}>
                      {CORRECT_LABELS.map((l, i) => <option key={i} value={i}>{l}</option>)}
                    </select>
                  </div>
                  {quizType === 'interpolated' && (
                    <div style={{ display: 'flex', gap: '1rem' }}>
                      <div>
                        <label className="admin-label">Timestamp (s)</label>
                        <input className="admin-input" type="number" value={d.timestamp ?? ''} onChange={e => setEditDraft(p => ({ ...p, timestamp: Number(e.target.value) }))} />
                      </div>
                      <div>
                        <label className="admin-label">Rewatch start (s)</label>
                        <input className="admin-input" type="number" value={d.rewatch_start ?? ''} onChange={e => setEditDraft(p => ({ ...p, rewatch_start: Number(e.target.value) }))} />
                      </div>
                    </div>
                  )}
                  <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
                    <button className="admin-btn admin-btn--primary" onClick={saveEdit} disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
                    <button className="admin-btn" onClick={cancelEdit}>Cancel</button>
                  </div>
                </div>
              ) : (
                <>
                  <p className="admin-question-text">{q.question_text}</p>
                  <div className="admin-options">
                    {(['option_a', 'option_b', 'option_c', 'option_d'] as const).map((key, i) => (
                      <div key={key} className={`admin-option ${i === q.correct_index ? 'admin-option--correct' : ''}`}>
                        <span className="admin-option-label">{CORRECT_LABELS[i]}</span>
                        {q[key]}
                      </div>
                    ))}
                  </div>
                  <QuestionExcerpt topic={q.topic} question={q} />
                  <GroundingEvidence topic={q.topic} citations={q.citations} />
                </>
              )}
            </div>
          )
        })}
      </section>
    </div>
  )
}
