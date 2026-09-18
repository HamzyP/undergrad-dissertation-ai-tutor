import { useCallback, useEffect, useRef, useState } from 'react'

function useCountUp(target: number, duration = 900): number {
  const [value, setValue] = useState(0)
  useEffect(() => {
    if (target === 0) { setValue(0); return }
    const start = performance.now()
    let raf: number
    const tick = (now: number) => {
      const progress = Math.min((now - start) / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3)
      setValue(Math.round(eased * target))
      if (progress < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, duration])
  return value
}

const API = 'http://127.0.0.1:8000/api'

interface Source {
  source_id: string
  source_type: 'url' | 'transcript'
  display_name: string
  url: string
  chunk_count: number
  accessed: string
  active: boolean
  ingested: boolean
}

interface CorpusData {
  total_chunks: number
  url_count: number
  transcript_count: number
  mean_tokens: number
  median_tokens: number
  sources: Source[]
}

interface QueryResult {
  rank: number
  distance: number
  source_id: string
  source_type: string
  location: string
  text: string
}

function normaliseCorpusData(data: unknown): CorpusData {
  const payload = typeof data === 'object' && data !== null ? data as Record<string, unknown> : {}
  const rawSources = Array.isArray(payload.sources) ? payload.sources : []

  return {
    total_chunks: typeof payload.total_chunks === 'number' ? payload.total_chunks : 0,
    url_count: typeof payload.url_count === 'number' ? payload.url_count : 0,
    transcript_count: typeof payload.transcript_count === 'number' ? payload.transcript_count : 0,
    mean_tokens: typeof payload.mean_tokens === 'number' ? payload.mean_tokens : 0,
    median_tokens: typeof payload.median_tokens === 'number' ? payload.median_tokens : 0,
    sources: rawSources
      .map((source): Source | null => {
        if (!source || typeof source !== 'object') return null
        const record = source as Record<string, unknown>
        const sourceId = typeof record.source_id === 'string' ? record.source_id : ''
        if (!sourceId) return null
        return {
          source_id: sourceId,
          source_type: record.source_type === 'transcript' ? 'transcript' : 'url',
          display_name: typeof record.display_name === 'string' && record.display_name
            ? record.display_name
            : sourceId,
          url: typeof record.url === 'string' ? record.url : '',
          chunk_count: typeof record.chunk_count === 'number' ? record.chunk_count : 0,
          accessed: typeof record.accessed === 'string' ? record.accessed : '',
          active: typeof record.active === 'boolean' ? record.active : false,
          ingested: typeof record.ingested === 'boolean' ? record.ingested : false,
        }
      })
      .filter((source): source is Source => source !== null),
  }
}

interface CorpusOverviewProps {
  corpus: CorpusData
  hoveredType: 'url' | 'transcript' | 'all' | null
  setHoveredType: (t: 'url' | 'transcript' | 'all' | null) => void
}

function CorpusOverview({ corpus, hoveredType, setHoveredType }: CorpusOverviewProps) {
  const urlPct = (corpus.url_count / corpus.total_chunks) * 100
  const transcriptPct = (corpus.transcript_count / corpus.total_chunks) * 100

  const animatedTotal = useCountUp(corpus.total_chunks)
  const animatedUrl = useCountUp(corpus.url_count)
  const animatedTranscript = useCountUp(corpus.transcript_count)

  return (
    <div>
      {/* Split bar — above the cards */}
      <div className="corpus-bar">
        {urlPct > 0 && (
          <div
            className={`corpus-bar__segment corpus-bar__segment--url${hoveredType === 'url' || hoveredType === 'all' ? ' corpus-bar__segment--hovered' : ''}${hoveredType && hoveredType !== 'url' && hoveredType !== 'all' ? ' corpus-bar__segment--dim' : ''}`}
            style={{ width: `${urlPct}%` }}
            onMouseEnter={() => setHoveredType('url')}
            onMouseLeave={() => setHoveredType(null)}
          >
            {urlPct > 5 && (
              <span className="corpus-bar__label">{animatedUrl.toLocaleString()}</span>
            )}
            <span className="corpus-bar__tooltip">
              URL · {corpus.url_count.toLocaleString()} chunks · {urlPct.toFixed(1)}%
            </span>
          </div>
        )}
        {transcriptPct > 0 && (
          <div
            className={`corpus-bar__segment corpus-bar__segment--transcript${hoveredType === 'transcript' || hoveredType === 'all' ? ' corpus-bar__segment--hovered' : ''}${hoveredType && hoveredType !== 'transcript' && hoveredType !== 'all' ? ' corpus-bar__segment--dim' : ''}`}
            style={{ width: `${transcriptPct}%` }}
            onMouseEnter={() => setHoveredType('transcript')}
            onMouseLeave={() => setHoveredType(null)}
          >
            {transcriptPct > 5 && (
              <span className="corpus-bar__label">{animatedTranscript.toLocaleString()}</span>
            )}
            <span className="corpus-bar__tooltip">
              Transcript · {corpus.transcript_count.toLocaleString()} chunks · {transcriptPct.toFixed(1)}%
            </span>
          </div>
        )}
      </div>

      {/* Stat cards */}
      <div className="corpus-stats">
        <div
          className={`corpus-stat corpus-stat--url${hoveredType === 'url' ? ' corpus-stat--active' : ''}${hoveredType && hoveredType !== 'url' ? ' corpus-stat--dim' : ''}`}
          onMouseEnter={() => setHoveredType('url')}
          onMouseLeave={() => setHoveredType(null)}
        >
          <span className="corpus-stat__value">{animatedUrl.toLocaleString()}</span>
          <span className="corpus-stat__label">URL chunks</span>
          <span className="corpus-stat__pct">{urlPct.toFixed(1)}%</span>
        </div>
        <div
          className={`corpus-stat corpus-stat--total${hoveredType === 'all' ? ' corpus-stat--active-all' : ''}`}
          onMouseEnter={() => setHoveredType('all')}
          onMouseLeave={() => setHoveredType(null)}
        >
          <span className="corpus-stat__value">{animatedTotal.toLocaleString()}</span>
          <span className="corpus-stat__label">total chunks</span>
          <span className="corpus-stat__sub">~{corpus.mean_tokens} avg tokens</span>
        </div>
        <div
          className={`corpus-stat corpus-stat--transcript${hoveredType === 'transcript' ? ' corpus-stat--active' : ''}${hoveredType && hoveredType !== 'transcript' ? ' corpus-stat--dim' : ''}`}
          onMouseEnter={() => setHoveredType('transcript')}
          onMouseLeave={() => setHoveredType(null)}
        >
          <span className="corpus-stat__value">{animatedTranscript.toLocaleString()}</span>
          <span className="corpus-stat__label">transcript chunks</span>
          <span className="corpus-stat__pct">{transcriptPct.toFixed(1)}%</span>
        </div>
      </div>

      {(() => {
        const m = corpus.median_tokens
        const MIN = 80
        const MAX = 450
        const SCALE = 600
        const pct = Math.min(m / SCALE * 100, 100)
        const minPct = MIN / SCALE * 100
        const maxPct = MAX / SCALE * 100
        const ok = m >= MIN && m <= MAX
        const statusLabel = m < MIN
          ? 'Too small — risk of poor context'
          : m > MAX
          ? 'Too large — risk of noisy retrieval'
          : 'Chunk size looks good'
        return (
          <div>
            <hr className="corpus-divider" />
            <p className="corpus-section-title">Chunk Size Health</p>
            <div className="chunk-health-header">
              <span className={`corpus-chunk-health__dot ${ok ? 'corpus-chunk-health__dot--ok' : 'corpus-chunk-health__dot--warn'}`} />
              <span className="admin-muted">{statusLabel}</span>
              <span className="chunk-health-median">median {m} tokens</span>
            </div>
            <div className="chunk-health-track">
              {/* danger zone left */}
              <div className="chunk-health-zone chunk-health-zone--danger" style={{ left: 0, width: `${minPct}%` }} />
              {/* good zone */}
              <div className="chunk-health-zone chunk-health-zone--good" style={{ left: `${minPct}%`, width: `${maxPct - minPct}%` }} />
              {/* danger zone right */}
              <div className="chunk-health-zone chunk-health-zone--danger" style={{ left: `${maxPct}%`, right: 0 }} />
              {/* threshold lines */}
              <div className="chunk-health-tick" style={{ left: `${minPct}%` }}>
                <span className="chunk-health-tick__label">{MIN}</span>
              </div>
              <div className="chunk-health-tick" style={{ left: `${maxPct}%` }}>
                <span className="chunk-health-tick__label">{MAX}</span>
              </div>
              {/* current median marker */}
              <div className={`chunk-health-marker ${ok ? 'chunk-health-marker--ok' : 'chunk-health-marker--warn'}`} style={{ left: `${pct}%` }} />
            </div>
            <div className="chunk-health-axis">
              <span>0</span>
              <span style={{ marginLeft: 'auto' }}>{SCALE}+ tokens</span>
            </div>
          </div>
        )
      })()}
    </div>
  )
}

export default function RagDebugTab() {
  const [corpus, setCorpus] = useState<CorpusData | null>(null)
  const [corpusError, setCorpusError] = useState('')
  const [corpusLoading, setCorpusLoading] = useState(true)

  // corpus bar hover
  const [hoveredType, setHoveredType] = useState<'url' | 'transcript' | 'all' | null>(null)

  // per-source deactivation / deletion
  const [deactivating, setDeactivating] = useState<string | null>(null)
  const [deactivateMsg, setDeactivateMsg] = useState<Record<string, string>>({})
  const [deleting, setDeleting] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)

  // add URL
  const [newUrl, setNewUrl] = useState('')
  const [newUrlTitle, setNewUrlTitle] = useState('')
  const [addingUrl, setAddingUrl] = useState(false)
  const [addUrlMsg, setAddUrlMsg] = useState('')
  const [addUrlError, setAddUrlError] = useState('')

  // run ingest
  const [ingesting, setIngesting] = useState(false)
  const [ingestMsg, setIngestMsg] = useState('')
  const [ingestError, setIngestError] = useState('')

  // transcript upload
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadMsg, setUploadMsg] = useState('')
  const [uploadError, setUploadError] = useState('')

  // query tester
  const [query, setQuery] = useState('')
  const [queryScope, setQueryScope] = useState<'all' | 'source'>('all')
  const [queryScopeSource, setQueryScopeSource] = useState('')
  const [results, setResults] = useState<QueryResult[]>([])
  const [queryError, setQueryError] = useState('')
  const [queryLoading, setQueryLoading] = useState(false)

  const loadCorpus = useCallback(() => {
    setCorpusLoading(true)
    setCorpusError('')
    fetch(`${API}/rag-debug/corpus/`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then(data => setCorpus(normaliseCorpusData(data)))
      .catch((e: unknown) => {
        setCorpus(null)
        setCorpusError(e instanceof Error ? e.message : String(e))
      })
      .finally(() => setCorpusLoading(false))
  }, [])

  useEffect(() => { loadCorpus() }, [loadCorpus])

  const handleDeactivate = async (source: Source) => {
    const key = `${source.source_type}:${source.source_id}`
    setDeactivating(key)
    setDeactivateMsg(prev => ({ ...prev, [key]: '' }))
    try {
      const r = await fetch(
        `${API}/rag-debug/sources/${source.source_type}/${source.source_id}/deactivate/`,
        { method: 'POST' }
      )
      const data = await r.json()
      if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`)
      setDeactivateMsg(prev => ({ ...prev, [key]: `Removed ${data.deleted} chunks.` }))
      loadCorpus()
    } catch (e: unknown) {
      setDeactivateMsg(prev => ({
        ...prev,
        [key]: `Error: ${e instanceof Error ? e.message : String(e)}`,
      }))
    } finally {
      setDeactivating(null)
    }
  }

  const handleDelete = async (source: Source) => {
    const key = `${source.source_type}:${source.source_id}`
    setDeleting(key)
    setConfirmDelete(null)
    try {
      const r = await fetch(
        `${API}/rag-debug/sources/${source.source_type}/${source.source_id}/`,
        { method: 'DELETE' }
      )
      const data = await r.json()
      if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`)
      loadCorpus()
    } catch (e: unknown) {
      setDeactivateMsg(prev => ({
        ...prev,
        [key]: `Error: ${e instanceof Error ? e.message : String(e)}`,
      }))
    } finally {
      setDeleting(null)
    }
  }

  const handleAddUrl = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newUrl.trim()) return
    setAddingUrl(true)
    setAddUrlMsg('')
    setAddUrlError('')
    try {
      const r = await fetch(`${API}/rag-debug/sources/url/add/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: newUrl.trim(), title: newUrlTitle.trim() }),
      })
      const data = await r.json()
      if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`)
      setAddUrlMsg(`Added "${data.title}" — run ingest to index it.`)
      setNewUrl('')
      setNewUrlTitle('')
      loadCorpus()
    } catch (e: unknown) {
      setAddUrlError(e instanceof Error ? e.message : String(e))
    } finally {
      setAddingUrl(false)
    }
  }

  const handleIngest = async () => {
    setIngesting(true)
    setIngestMsg('')
    setIngestError('')
    try {
      const r = await fetch(`${API}/rag-debug/sources/url/ingest/`, { method: 'POST' })
      const data = await r.json()
      if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`)
      const ingested: { source_id: string; chunks: number }[] = data.ingested ?? []
      const errors: { source_id: string; error: string }[] = data.errors ?? []
      if (ingested.length === 0 && errors.length === 0) {
        setIngestMsg(data.message || 'Nothing to ingest.')
      } else {
        const parts: string[] = []
        if (ingested.length) parts.push(`Ingested ${ingested.length} source(s): ${ingested.map(i => `${i.source_id} (${i.chunks} chunks)`).join(', ')}.`)
        if (errors.length) parts.push(`Errors: ${errors.map(e => `${e.source_id}: ${e.error}`).join('; ')}.`)
        setIngestMsg(parts.join(' '))
      }
      loadCorpus()
    } catch (e: unknown) {
      setIngestError(e instanceof Error ? e.message : String(e))
    } finally {
      setIngesting(false)
    }
  }

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault()
    const file = fileInputRef.current?.files?.[0]
    if (!file) return
    setUploading(true)
    setUploadMsg('')
    setUploadError('')
    const form = new FormData()
    form.append('file', file)
    try {
      const r = await fetch(`${API}/rag-debug/upload/transcript/`, { method: 'POST', body: form })
      const data = await r.json()
      if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`)
      setUploadMsg(`Stored ${data.chunks_stored} chunks for "${data.source_id}".`)
      if (fileInputRef.current) fileInputRef.current.value = ''
      loadCorpus()
    } catch (e: unknown) {
      setUploadError(e instanceof Error ? e.message : String(e))
    } finally {
      setUploading(false)
    }
  }

  const handleQuery = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!query.trim()) return
    setQueryLoading(true)
    setQueryError('')
    setResults([])
    let source_type: string | null = null
    let source_id: string | null = null
    if (queryScope === 'source' && queryScopeSource) {
      const [stype, ...rest] = queryScopeSource.split(':')
      source_type = stype
      source_id = rest.join(':')
    }
    try {
      const r = await fetch(`${API}/rag-debug/query/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, source_type, source_id }),
      })
      const data = await r.json()
      if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`)
      setResults(data.results)
    } catch (e: unknown) {
      setQueryError(e instanceof Error ? e.message : String(e))
    } finally {
      setQueryLoading(false)
    }
  }

  const pendingCount = corpus?.sources.filter(s => s.source_type === 'url' && !s.ingested).length ?? 0
  const activeSources = corpus?.sources.filter(s => s.active) ?? []

  return (
    <div className="admin-panels">

      {/* Panel 1: Corpus overview */}
      <section className="admin-panel">
        <h3>Corpus Overview</h3>
        {corpusLoading && <p className="admin-muted">Loading…</p>}
        {corpusError && (
          <>
            <p className="admin-error">Error: {corpusError}</p>
            <button className="admin-btn" type="button" onClick={loadCorpus}>Retry</button>
          </>
        )}
        {corpus && corpus.total_chunks > 0 && (
          <CorpusOverview corpus={corpus} hoveredType={hoveredType} setHoveredType={setHoveredType} />
        )}
        {corpus && corpus.total_chunks === 0 && (
          <p className="admin-muted">Corpus is empty. Add sources and run ingest.</p>
        )}
        {!corpusLoading && !corpusError && !corpus && (
          <p className="admin-muted">No corpus overview available.</p>
        )}
      </section>

      {/* Panel 2: Source management */}
      <section className="admin-panel">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
          <h3 style={{ margin: 0 }}>Sources</h3>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <button
              className="admin-btn admin-btn--primary"
              type="button"
              onClick={handleIngest}
              disabled={ingesting}
            >
              {ingesting ? 'Ingesting…' : `Run Ingest${pendingCount > 0 ? ` (${pendingCount} pending)` : ''}`}
            </button>
            {ingestMsg && <span className="admin-success" style={{ fontSize: '0.82rem' }}>{ingestMsg}</span>}
            {ingestError && <span className="admin-error" style={{ fontSize: '0.82rem' }}>Error: {ingestError}</span>}
          </div>
        </div>

        {/* Add URL */}
        <p className="admin-label" style={{ marginBottom: '0.4rem' }}>
          Add URL Source <span className="admin-muted">(any webpage)</span>
        </p>
        <form onSubmit={handleAddUrl} style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginBottom: '0.5rem' }}>
          <input
            className="admin-input"
            style={{ flex: 2 }}
            value={newUrl}
            onChange={e => setNewUrl(e.target.value)}
            placeholder="https://example.com/article"
            type="url"
          />
          <input
            className="admin-input"
            style={{ flex: 1 }}
            value={newUrlTitle}
            onChange={e => setNewUrlTitle(e.target.value)}
            placeholder="Title (optional)"
          />
          <button className="admin-btn admin-btn--primary" type="submit" disabled={addingUrl || !newUrl.trim()}>
            {addingUrl ? 'Adding…' : 'Add URL'}
          </button>
        </form>
        {addUrlMsg && <p className="admin-success" style={{ marginBottom: '0.5rem' }}>{addUrlMsg}</p>}
        {addUrlError && <p className="admin-error" style={{ marginBottom: '0.5rem' }}>Error: {addUrlError}</p>}

        {/* Divider */}
        <hr style={{ border: 'none', borderTop: '1px solid var(--border)', margin: '0.75rem 0' }} />

        {/* Upload transcript */}
        <p className="admin-label" style={{ marginBottom: '0.4rem' }}>
          Upload Transcript <span className="admin-muted">(WebVTT .vtt file)</span>
        </p>
        <form onSubmit={handleUpload} style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginBottom: '0.75rem' }}>
          <input ref={fileInputRef} type="file" accept=".vtt" className="admin-input" style={{ flex: 1 }} />
          <button className="admin-btn" type="submit" disabled={uploading}>
            {uploading ? 'Uploading…' : 'Upload .vtt'}
          </button>
        </form>
        {uploadMsg && <p className="admin-success" style={{ marginBottom: '0.5rem' }}>{uploadMsg}</p>}
        {uploadError && <p className="admin-error" style={{ marginBottom: '0.5rem' }}>Error: {uploadError}</p>}

        <hr style={{ border: 'none', borderTop: '1px solid var(--border)', margin: '0.75rem 0 0.5rem' }} />
        <p className="corpus-section-title">Ingested Sources</p>

        {corpus && (
          corpus.sources.length > 0 ? (
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Title / Topic</th>
                  <th>Chunks</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {corpus.sources.map(s => {
                  const key = `${s.source_type}:${s.source_id}`
                  const msg = deactivateMsg[key]
                  return (
                    <tr key={key} style={{ opacity: s.ingested ? 1 : 0.55 }}>
                      <td>
                        <span className={`admin-badge admin-badge--${s.source_type}`}>{s.source_type}</span>
                      </td>
                      <td>
                        {s.url
                          ? (
                            <a
                              href={s.source_type === 'transcript' ? `http://127.0.0.1:8000${s.url}` : s.url}
                              target="_blank"
                              rel="noreferrer"
                              style={{ color: 'var(--accent)' }}
                            >
                              {s.display_name}
                            </a>
                          )
                          : s.display_name
                        }
                      </td>
                      <td className="admin-num">{s.chunk_count}</td>
                      <td>
                        {s.ingested
                          ? <span className="admin-badge admin-badge--ingested">ingested</span>
                          : <span className="admin-badge admin-badge--pending">pending</span>
                        }
                        {s.ingested && !s.active && (
                          <span className="admin-muted" style={{ marginLeft: '0.4rem', fontSize: '0.78rem' }}>(inactive)</span>
                        )}
                      </td>
                      <td style={{ whiteSpace: 'nowrap' }}>
                        {msg && (
                          <span
                            className={msg.startsWith('Error') ? 'admin-error' : 'admin-success'}
                            style={{ marginRight: '0.5rem', fontSize: '0.78rem' }}
                          >
                            {msg}
                          </span>
                        )}
                        {s.active && (
                          <button
                            className="admin-btn admin-btn--danger admin-btn--sm"
                            type="button"
                            disabled={deactivating === key || deleting === key}
                            onClick={() => handleDeactivate(s)}
                            style={{ marginRight: '0.25rem' }}
                          >
                            {deactivating === key ? '…' : 'Deactivate'}
                          </button>
                        )}
                        {confirmDelete === key ? (
                          <>
                            <button
                              className="admin-btn admin-btn--danger admin-btn--sm"
                              type="button"
                              disabled={deleting === key}
                              onClick={() => handleDelete(s)}
                              style={{ marginRight: '0.25rem' }}
                            >
                              {deleting === key ? '…' : 'Confirm'}
                            </button>
                            <button
                              className="admin-btn admin-btn--sm"
                              type="button"
                              onClick={() => setConfirmDelete(null)}
                            >
                              Cancel
                            </button>
                          </>
                        ) : (
                          <button
                            className="admin-btn admin-btn--sm"
                            type="button"
                            disabled={deleting === key}
                            onClick={() => setConfirmDelete(key)}
                          >
                            Delete
                          </button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          ) : (
            <p className="admin-muted">No sources yet. Add a URL or upload a transcript above.</p>
          )
        )}
        {!corpusLoading && !corpusError && !corpus && (
          <p className="admin-muted">No source list available.</p>
        )}
      </section>

      {/* Panel 3: Query tester */}
      <section className="admin-panel">
        <h3>Query Tester</h3>
        <p className="admin-muted" style={{ marginBottom: '0.75rem' }}>
          Routed through: normalise → <code>search_query:</code> prefix → nomic-embed-text → cosine top-5. Ollama must be running.
        </p>

        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginBottom: '0.75rem' }}>
          <label className="admin-label" style={{ margin: 0 }}>Search in:</label>
          <select
            className="admin-select"
            style={{ flex: 1 }}
            value={queryScope === 'all' ? 'all' : queryScopeSource}
            onChange={e => {
              if (e.target.value === 'all') {
                setQueryScope('all')
                setQueryScopeSource('')
              } else {
                setQueryScope('source')
                setQueryScopeSource(e.target.value)
              }
            }}
          >
            <option value="all">All sources</option>
            {activeSources.map(s => (
              <option key={`${s.source_type}:${s.source_id}`} value={`${s.source_type}:${s.source_id}`}>
                [{s.source_type}] {s.display_name}
              </option>
            ))}
          </select>
        </div>

        <form onSubmit={handleQuery} style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
          <input
            className="admin-input"
            style={{ flex: 1 }}
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="e.g. What is the Harm Principle?"
          />
          <button className="admin-btn" type="submit" disabled={queryLoading}>
            {queryLoading ? 'Searching…' : 'Search'}
          </button>
        </form>

        {queryError && <p className="admin-error">Error: {queryError}</p>}
        {results.map(r => (
          <div key={r.rank} className="admin-result-card">
            <div className="admin-result-header">
              <span className="admin-result-rank">#{r.rank}</span>
              <span className="admin-result-dist">dist {r.distance}</span>
              <code>{r.source_id}</code>
              <span className={`admin-badge admin-badge--${r.source_type}`}>{r.source_type}</span>
              {r.location && <span className="admin-muted">{r.location}</span>}
            </div>
            <p className="admin-result-text">{r.text}</p>
          </div>
        ))}
        {!queryLoading && results.length === 0 && query && !queryError && (
          <p className="admin-muted">No results.</p>
        )}
      </section>
    </div>
  )
}
