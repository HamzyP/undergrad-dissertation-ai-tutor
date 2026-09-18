import { useRef, useState } from 'react'
import type { ChatMessage, ConsolidationQuestionData, CitationData } from '../Chat'
import { logTutorConsoleError } from '../lib/tutorUtils'

interface ChatApiResponse {
  response: string
  citations: CitationData[]
  latency_ms: number
}

interface ChatStreamEvent {
  type: 'delta' | 'replace' | 'final' | 'error'
  text?: string
  message?: string
  citations?: CitationData[]
  latency_ms?: number
}

interface RequestTutorReplyOptions {
  message: string
  scaffoldLevel: string
  timestamp: number
  history: ChatMessage[]
  topic: string
  sessionId: string
  model?: string
  interpolatedQuestion?: string
  interpolatedAnswerCorrect?: boolean
  explanationOutcome?: 'correct' | 'partial' | 'incorrect'
  explanationAttempt?: number
  explanationGap?: string
  questionClassification?: string
  supportStrategy?: string
  hintLevel?: number
}

export function useTutorChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isTutorLoading, setIsTutorLoading] = useState(false)
  const nextMessageIdRef = useRef(1)
  const messageTimestampsRef = useRef<Map<number, string>>(new Map())

  const nextId = () => nextMessageIdRef.current++
  const stampNow = (id: number) => messageTimestampsRef.current.set(id, new Date().toISOString())

  const addTextMessage = (
    sender: 'user' | 'tutor',
    text: string,
    citations?: CitationData[],
    pending?: boolean,
  ) => {
    const id = nextId()
    stampNow(id)
    setMessages(prev => [...prev, { id, sender, type: 'text', text, citations, pending }])
    return id
  }

  const addConsolidationMessage = (data: ConsolidationQuestionData) => {
    const id = nextId()
    stampNow(id)
    setMessages(prev => [...prev, { id, sender: 'tutor', type: 'consolidation', data }])
  }

  const addChoiceMessage = (text: string) => {
    const id = nextId()
    stampNow(id)
    setMessages(prev => [...prev, { id, sender: 'tutor', type: 'choice', text }])
  }

  const addInterventionMessage = (text: string) => {
    const id = nextId()
    stampNow(id)
    setMessages(prev => [...prev, { id, sender: 'tutor', type: 'intervention', text }])
  }

  // Only text messages are sent to the backend as history
  const getTextHistory = (msgs: ChatMessage[]): { sender: string; text: string }[] =>
    msgs
      .filter((m): m is ChatMessage & { type: 'text' } => m.type === 'text')
      .map(m => ({ sender: m.sender, text: m.text }))

  const requestTutorReply = async (opts: RequestTutorReplyOptions): Promise<ChatApiResponse | null> => {
    const {
      message, scaffoldLevel, timestamp, history, topic, sessionId, model,
      interpolatedQuestion, interpolatedAnswerCorrect,
      explanationOutcome, explanationAttempt, explanationGap,
      questionClassification, supportStrategy, hintLevel,
    } = opts

    console.debug('[chat] requestTutorReply called', { message, scaffoldLevel, timestamp, topic, interpolatedQuestion })

    const tutorMessageId = addTextMessage('tutor', '', [], true)
    console.debug('[chat] pending tutor message created, id=', tutorMessageId)

    const updateTutorMessage = (
      updater: (current: { text: string; citations?: CitationData[]; pending?: boolean }) => {
        text?: string
        citations?: CitationData[]
        pending?: boolean
      },
    ) => {
      setMessages(prev =>
        prev.map(msg => {
          if (msg.id !== tutorMessageId || msg.type !== 'text') return msg
          return { ...msg, ...updater(msg) }
        }),
      )
    }

    const finalizeTutorMessage = (text: string, citations: CitationData[] = []) => {
      updateTutorMessage(() => ({ text, citations, pending: false }))
    }

    setIsTutorLoading(true)
    const t0 = performance.now()
    const elapsed = () => ((performance.now() - t0) / 1000).toFixed(2) + 's'
    console.debug('[chat] fetching stream from backend...')

    // Heartbeat: warn every 10s while we haven't seen any bytes from the backend.
    let lastActivity = performance.now()
    const heartbeat = window.setInterval(() => {
      const idle = (performance.now() - lastActivity) / 1000
      if (idle > 10) {
        console.warn(`[chat] still waiting for backend (idle ${idle.toFixed(1)}s, total ${elapsed()})`)
      }
    }, 5000)

    try {
      const response = await fetch('http://127.0.0.1:8000/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          message,
          topic,
          timestamp,
          current_scaffold_level: scaffoldLevel,
          history: getTextHistory(history),
          ...(interpolatedQuestion ? { interpolated_question: interpolatedQuestion } : {}),
          ...(interpolatedAnswerCorrect ? { interpolated_answer_correct: true } : {}),
          ...(explanationOutcome ? { explanation_outcome: explanationOutcome } : {}),
          ...(explanationAttempt !== undefined ? { explanation_attempt: explanationAttempt } : {}),
          ...(explanationGap ? { explanation_gap: explanationGap } : {}),
          ...(questionClassification ? { question_classification: questionClassification } : {}),
          ...(supportStrategy ? { support_strategy: supportStrategy } : {}),
          ...(hintLevel !== undefined ? { hint_level: hintLevel } : {}),
          ...(model ? { model } : {}),
        }),
      })
      lastActivity = performance.now()

      console.debug(`[chat] response received in ${elapsed()}, status=`, response.status, 'ok=', response.ok)
      if (!response.ok) throw new Error(`Tutor backend returned ${response.status}`)
      if (!response.body) throw new Error('Tutor backend did not provide a stream')

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let streamedText = ''
      let finalData: ChatApiResponse | null = null
      let firstDeltaSeen = false

      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        lastActivity = performance.now()
        buffer += decoder.decode(value, { stream: true })

        let newlineIndex = buffer.indexOf('\n')
        while (newlineIndex !== -1) {
          const line = buffer.slice(0, newlineIndex).trim()
          buffer = buffer.slice(newlineIndex + 1)

          if (line) {
            const event: ChatStreamEvent = JSON.parse(line)
            if (event.type === 'delta' && !firstDeltaSeen) {
              firstDeltaSeen = true
              console.debug(`[chat] first token at ${elapsed()}`)
            }
            console.debug(`[chat] stream event @${elapsed()}:`, event.type, event.type === 'delta' ? `+${event.text?.length ?? 0}chars` : event)
            if (event.type === 'delta' && event.text) {
              streamedText += event.text
              updateTutorMessage(current => ({ text: current.text + event.text }))
            } else if (event.type === 'replace') {
              streamedText = event.text ?? ''
              updateTutorMessage(() => ({ text: event.text ?? '' }))
            } else if (event.type === 'final') {
              finalData = {
                response: event.text ?? '',
                citations: event.citations ?? [],
                latency_ms: event.latency_ms ?? 0,
              }
              console.debug('[chat] final event received, latency_ms=', finalData.latency_ms, 'text length=', finalData.response.length)
              finalizeTutorMessage(finalData.response, finalData.citations)
            } else if (event.type === 'error') {
              logTutorConsoleError('CHAT_STREAM', 'Backend streamed an explicit error event.', {
                topic, message, timestamp, backendMessage: event.message ?? null,
              })
              finalizeTutorMessage(event.message ?? 'Temporary debug error: backend chat request failed.')
            }
          }

          newlineIndex = buffer.indexOf('\n')
        }
      }

      console.debug('[chat] stream reader done, finalData=', !!finalData, 'streamedText length=', streamedText.length)
      if (!finalData) {
        if (!streamedText) {
          logTutorConsoleError('CHAT_STREAM', 'Stream ended without a final reply and without any partial text.', {
            topic, message, timestamp,
          })
          finalizeTutorMessage('Temporary debug error: backend chat request failed.')
        } else {
          logTutorConsoleError('CHAT_STREAM', 'Stream ended without a final reply; showing partial tutor text.', {
            topic, message, timestamp, partialText: streamedText,
          })
          updateTutorMessage(current => ({ pending: false, text: current.text }))
        }
      }

      return finalData
    } catch (error) {
      logTutorConsoleError('CHAT_REQUEST', 'Tutor backend request failed.', {
        topic, message, timestamp, interpolatedQuestion: interpolatedQuestion ?? null, error,
      })
      finalizeTutorMessage('Temporary debug error: backend chat request failed.')
      return null
    } finally {
      window.clearInterval(heartbeat)
      console.debug(`[chat] request finished in ${elapsed()}`)
      setIsTutorLoading(false)
    }
  }

  return {
    messages,
    isTutorLoading,
    addTextMessage,
    addConsolidationMessage,
    addChoiceMessage,
    addInterventionMessage,
    requestTutorReply,
    nextMessageId: () => nextMessageIdRef.current - 1,
    getMessageTimestamp: (id: number) => messageTimestampsRef.current.get(id) ?? new Date().toISOString(),
  }
}
