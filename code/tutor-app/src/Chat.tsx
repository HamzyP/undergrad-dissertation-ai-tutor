import { useState, useRef, useEffect } from 'react'

export interface CitationData {
  source_type: 'sep' | 'transcript'
  source_id: string
  title: string
  url: string
  location: string
  start_time: number | null
}

export interface ConsolidationQuestionData {
  question: string
  options: string[]
  correctIndex: number
  citations: CitationData[]
}

interface TextMessage {
  id: number
  sender: 'user' | 'tutor'
  type: 'text'
  text: string
  citations?: CitationData[]
  pending?: boolean
}

interface ConsolidationMessage {
  id: number
  sender: 'tutor'
  type: 'consolidation'
  data: ConsolidationQuestionData
}

interface ChoiceMessage {
  id: number
  sender: 'tutor'
  type: 'choice'
  text: string
}

interface InterventionMessage {
  id: number
  sender: 'tutor'
  type: 'intervention'
  text: string
}

export type ChatMessage = TextMessage | ConsolidationMessage | ChoiceMessage | InterventionMessage

interface ChatProps {
  messages: ChatMessage[]
  onSend: (text: string) => void
  onConsolidationAnswer: (messageId: number, selectedIndex: number) => void
  onChoice: (choice: 'discuss' | 'continue') => void
  onIntervention: (choice: 'rewatch' | 'hint') => void
  onSeekVideo?: (time: number) => void
  disabled?: boolean
}

function ConsolidationCard({
  data,
  onAnswer,
  onSeekVideo,
  active,
}: {
  data: ConsolidationQuestionData
  onAnswer: (selectedIndex: number) => void
  onSeekVideo?: (time: number) => void
  active: boolean
}) {
  const [selected, setSelected] = useState<number | null>(null)
  const [submitted, setSubmitted] = useState(false)

  const handleSubmit = () => {
    if (selected === null || submitted || !active) return
    setSubmitted(true)
    onAnswer(selected)
  }

  const isCorrect = submitted && selected === data.correctIndex

  return (
    <div className="consolidation-card">
      <div className="consolidation-question">
        {data.citations && data.citations.length > 0 ? (
          <CitedText text={data.question} citations={data.citations} onSeekVideo={onSeekVideo} />
        ) : (
          <p>{data.question}</p>
        )}
      </div>
      <div className="consolidation-options" role="radiogroup">
        {data.options.map((option, index) => (
          <label
            key={index}
            className={`consolidation-option${selected === index ? ' selected' : ''}${
              submitted && index === data.correctIndex ? ' correct' : ''
            }${submitted && selected === index && index !== data.correctIndex ? ' incorrect' : ''}`}
          >
            <input
              type="radio"
              name={`consolidation-${data.question}`}
              checked={selected === index}
              onChange={() => setSelected(index)}
              disabled={submitted || !active}
            />
            <span>{option}</span>
          </label>
        ))}
      </div>
      {!submitted && active && (
        <button
          className="consolidation-submit"
          onClick={handleSubmit}
          disabled={selected === null}
        >
          Submit
        </button>
      )}
      {submitted && (
        <p className={`consolidation-feedback ${isCorrect ? 'correct' : 'incorrect'}`}>
          {isCorrect
            ? 'Correct!'
            : `Not quite — the answer is: ${data.options[data.correctIndex]}`}
        </p>
      )}
    </div>
  )
}

function InterventionButtons({ onIntervention, active }: { onIntervention: (choice: 'rewatch' | 'hint') => void; active: boolean }) {
  const [chosen, setChosen] = useState(false)
  const disabled = !active || chosen

  const handle = (choice: 'rewatch' | 'hint') => {
    if (disabled) return
    setChosen(true)
    onIntervention(choice)
  }

  return (
    <div className="choice-buttons">
      <button onClick={() => handle('rewatch')} disabled={disabled} className="choice-btn">
        Rewatch section
      </button>
      <button onClick={() => handle('hint')} disabled={disabled} className="choice-btn">
        Give me a hint
      </button>
    </div>
  )
}

function ChoiceButtons({ onChoice, active }: { onChoice: (choice: 'discuss' | 'continue') => void; active: boolean }) {
  const [chosen, setChosen] = useState(false)
  const disabled = !active || chosen

  const handle = (choice: 'discuss' | 'continue') => {
    if (disabled) return
    setChosen(true)
    onChoice(choice)
  }

  return (
    <div className="choice-buttons">
      <button onClick={() => handle('discuss')} disabled={disabled} className="choice-btn">
        Discuss further
      </button>
      <button onClick={() => handle('continue')} disabled={disabled} className="choice-btn">
        Continue watching
      </button>
    </div>
  )
}

/** Parse text containing [1], [2] etc. into segments of plain text and citation markers. */
function parseInlineCitations(text: string): Array<{ type: 'text'; value: string } | { type: 'cite'; index: number }> {
  const parts: Array<{ type: 'text'; value: string } | { type: 'cite'; index: number }> = []
  const regex = /\[(\d+)\]/g
  let lastIndex = 0
  let match: RegExpExecArray | null

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push({ type: 'text', value: text.slice(lastIndex, match.index) })
    }
    parts.push({ type: 'cite', index: parseInt(match[1], 10) })
    lastIndex = regex.lastIndex
  }

  if (lastIndex < text.length) {
    parts.push({ type: 'text', value: text.slice(lastIndex) })
  }

  return parts
}

function InlineCiteBadge({ index, citation, onSeekVideo }: { index: number; citation?: CitationData; onSeekVideo?: (time: number) => void }) {
  const isTranscript = citation?.source_type === 'transcript'
  const isClickable = citation?.url || (isTranscript && citation?.start_time != null && onSeekVideo)

  const handleClick = (e: React.MouseEvent) => {
    if (isTranscript && citation?.start_time != null && onSeekVideo) {
      e.preventDefault()
      onSeekVideo(citation.start_time)
    }
  }

  const inner = (
    <span
      className={`cite-badge cite-badge--${citation?.source_type ?? 'unknown'}${isClickable ? ' cite-badge--clickable' : ''}`}
      onClick={isTranscript ? handleClick : undefined}
    >
      {index}
      {citation && (
        <span className="cite-tooltip">
          <span className="cite-tooltip-title">{citation.title}</span>
          {citation.location && <span className="cite-tooltip-location">{citation.location}</span>}
          {citation.url && <span className="cite-tooltip-hint">Click to open article</span>}
          {isTranscript && citation.start_time != null && <span className="cite-tooltip-hint">Click to jump to this part of the video</span>}
        </span>
      )}
    </span>
  )

  if (citation?.url) {
    return (
      <a href={citation.url} target="_blank" rel="noopener noreferrer" className="cite-badge-link">
        {inner}
      </a>
    )
  }
  return inner
}

function CitedText({ text, citations, onSeekVideo }: { text: string; citations: CitationData[]; onSeekVideo?: (time: number) => void }) {
  const usedIndices = new Set<number>()

  const lines = text.split('\n')
  const rendered = lines.map((line, lineIdx) => {
    if (!line) return <p key={lineIdx}><br /></p>

    const parts = parseInlineCitations(line)
    return (
      <p key={lineIdx}>
        {parts.map((part, partIdx) => {
          if (part.type === 'text') return <span key={partIdx}>{part.value}</span>
          usedIndices.add(part.index)
          return (
            <InlineCiteBadge
              key={partIdx}
              index={part.index}
              citation={citations[part.index - 1]}
              onSeekVideo={onSeekVideo}
            />
          )
        })}
      </p>
    )
  })

  // Collect used citations for the reference list
  const refs = citations
    .map((c, i) => ({ ...c, num: i + 1 }))
    .filter(c => usedIndices.has(c.num))

  return (
    <div>
      <div className="chat-text">{rendered}</div>
      {refs.length > 0 && (
        <div className="cite-reflist">
          {refs.map(ref => (
            <div key={ref.num} className="cite-ref">
              <span className={`cite-ref-num cite-ref-num--${ref.source_type}`}>[{ref.num}]</span>
              <div className="cite-ref-body">
                {ref.url ? (
                  <a href={ref.url} target="_blank" rel="noopener noreferrer" className="cite-ref-title">
                    {ref.title}
                  </a>
                ) : ref.source_type === 'transcript' && ref.start_time != null && onSeekVideo ? (
                  <button className="cite-ref-seek" onClick={() => onSeekVideo(ref.start_time!)}>
                    {ref.title}
                  </button>
                ) : (
                  <span className="cite-ref-title">{ref.title}</span>
                )}
                {ref.location && (
                  ref.source_type === 'transcript' && ref.start_time != null && onSeekVideo ? (
                    <button className="cite-ref-seek cite-ref-location" onClick={() => onSeekVideo(ref.start_time!)}>
                      {ref.location}
                    </button>
                  ) : (
                    <span className="cite-ref-location">{ref.location}</span>
                  )
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function Chat({ messages, onSend, onConsolidationAnswer, onChoice, onIntervention, onSeekVideo, disabled }: ChatProps) {
  const [input, setInput] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to the latest message whenever messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = () => {
    const trimmed = input.trim()
    if (!trimmed) return
    onSend(trimmed)
    setInput('')
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      handleSend()
    }
  }

  return (
    <div className="chat">
      <div className="chat-messages" role="log" aria-live="polite" aria-label="Chat messages">
        {messages.length === 0 ? (
          <p className="chat-empty">Your tutor will respond here.</p>
        ) : (
          messages.map((msg, idx) => {
            const isLastOfType = (type: string) =>
              msg.type === type &&
              !messages.slice(idx + 1).some(m => m.type === type)
            return (
            <div key={msg.id} className={`chat-message chat-message-${msg.sender}`}>
              <span className="chat-sender">{msg.sender === 'user' ? 'You' : 'Tutor'}</span>
              {msg.type === 'consolidation' ? (
                <ConsolidationCard
                  data={msg.data}
                  onAnswer={(selectedIndex) => onConsolidationAnswer(msg.id, selectedIndex)}
                  onSeekVideo={onSeekVideo}
                  active={isLastOfType('consolidation')}
                />
              ) : msg.type === 'choice' ? (
                <div>
                  <div className="chat-text">
                    {msg.text.split('\n').map((line, i) => (
                      <p key={i}>{line || <br />}</p>
                    ))}
                  </div>
                  <ChoiceButtons onChoice={onChoice} active={isLastOfType('choice')} />
                </div>
              ) : msg.type === 'intervention' ? (
                <div>
                  <div className="chat-text">
                    {msg.text.split('\n').map((line, i) => (
                      <p key={i}>{line || <br />}</p>
                    ))}
                  </div>
                  <InterventionButtons onIntervention={onIntervention} active={isLastOfType('intervention')} />
                </div>
              ) : msg.type === 'text' && msg.citations && msg.citations.length > 0 ? (
                <CitedText text={msg.text} citations={msg.citations} onSeekVideo={onSeekVideo} />
              ) : (
                <div className="chat-text">
                  {msg.type === 'text' && msg.text.split('\n').map((line, i) => (
                    <p key={i}>{line || <br />}</p>
                  ))}
                  {msg.type === 'text' && msg.pending && (
                    <div className="chat-loading">
                      <span className="chat-spinner" aria-hidden="true" />
                      <span>{msg.text ? 'Generating more...' : 'Thinking...'}</span>
                    </div>
                  )}
                </div>
              )}
            </div>
            )
          })
        )}
        <div ref={messagesEndRef} />
      </div>
      <div className="chat-input">
        <input
          type="text"
          placeholder="Type your message..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          aria-label="Chat message input"
        />
        <button onClick={handleSend} disabled={disabled || !input.trim()} aria-label="Send message">
          Send
        </button>
      </div>
    </div>
  )
}

export default Chat
