import type { CitationData } from '../Chat'

// Scaffold scoring

export function scoreToLevel(score: number): number {
  if (score < -0.5) return 1
  if (score < 0.5) return 2
  if (score < 1.5) return 3
  if (score < 2.5) return 4
  return 5
}

export const levelLabels: Record<number, string> = {
  1: 'Full Support',
  2: 'High Support',
  3: 'Moderate Support',
  4: 'Low Support',
  5: 'Minimal Support',
}

// Explanation quality

export type ExplanationOutcome = 'correct' | 'partial' | 'incorrect'

const EXPLANATION_STOPWORDS = new Set([
  'a', 'an', 'and', 'are', 'as', 'at', 'be', 'because', 'but', 'by', 'for', 'from',
  'how', 'i', 'if', 'in', 'is', 'it', 'its', 'of', 'on', 'or', 'our', 'so', 'that',
  'the', 'their', 'them', 'there', 'they', 'this', 'to', 'we', 'what', 'when', 'which',
  'why', 'with', 'would', 'you', 'your',
])

const UNCERTAINTY_PATTERNS = [
  /\bidk\b/i,
  /\bi don't know\b/i,
  /\bi dont know\b/i,
  /\bnot sure\b/i,
  /\bunsure\b/i,
  /\bno idea\b/i,
  /\bconfused\b/i,
]

const EXPLANATION_CUE_PATTERNS = [
  /\bbecause\b/i,
  /\bmeans\b/i,
  /\bso that\b/i,
  /\bin order to\b/i,
  /\ballows\b/i,
  /\blimits\b/i,
  /\brestrict/i,
  /\bprotect/i,
  /\bprevent/i,
  /\bharm\b/i,
]

function normalizeExplanation(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9\s]/g, ' ').replace(/\s+/g, ' ').trim()
}

function explanationTokens(text: string): Set<string> {
  return new Set(
    normalizeExplanation(text)
      .split(' ')
      .filter(token => token.length > 3 && !EXPLANATION_STOPWORDS.has(token)),
  )
}

export function explanationsOverlap(a: string, b: string): boolean {
  const normalizedA = normalizeExplanation(a)
  const normalizedB = normalizeExplanation(b)
  if (!normalizedA || !normalizedB) return false
  if (normalizedA === normalizedB) return true

  const tokensA = explanationTokens(a)
  const tokensB = explanationTokens(b)
  if (tokensA.size === 0 || tokensB.size === 0) return false

  let overlap = 0
  tokensA.forEach(token => {
    if (tokensB.has(token)) overlap += 1
  })

  return overlap / Math.min(tokensA.size, tokensB.size) >= 0.8
}

function isClarifyingQuestion(text: string): boolean {
  const normalized = text.trim().toLowerCase()
  if (!normalized) return false
  if (normalized.endsWith('?')) return true

  const questionOpeners = [
    'what is', 'what does', 'how does', 'why is', 'why does',
    'can you explain', 'could you explain',
  ]
  return questionOpeners.some(opener => normalized.startsWith(opener))
}

function showsUncertainty(text: string): boolean {
  return UNCERTAINTY_PATTERNS.some(pattern => pattern.test(text))
}

export function isAcceptableReasoning(text: string): boolean {
  if (showsUncertainty(text) || isClarifyingQuestion(text)) return false
  const tokens = explanationTokens(text)
  if (tokens.size < 3) return false
  return EXPLANATION_CUE_PATTERNS.some(pattern => pattern.test(text))
}

export function fallbackExplanationOutcome(text: string): ExplanationOutcome {
  if (showsUncertainty(text) || isClarifyingQuestion(text)) return 'incorrect'

  const tokens = explanationTokens(text)
  const hasReasoningCue = EXPLANATION_CUE_PATTERNS.some(pattern => pattern.test(text))

  if (tokens.size >= 5 && hasReasoningCue) return 'correct'
  if (tokens.size >= 3 || hasReasoningCue) return 'partial'
  return 'incorrect'
}

// Logging

export function logTutorConsoleError(
  scope: string,
  message: string,
  details?: Record<string, unknown>,
) {
  const header = `*** TUTOR ERROR [${scope}] ${message} ***`
  if (details) {
    console.error(header, details)
  } else {
    console.error(header)
  }
}

// Types

export interface PendingExplanation {
  questionId: number
  attempts: number
}

export interface ConsolidationApiQuestion {
  question: string
  options: string[]
  correct_index: number
  citations: CitationData[]
}

export interface ConsolidationState {
  kind: 'consolidation' | 'mastery' | 'discussion_check'
  conceptId: number
  questions: ConsolidationApiQuestion[]
  currentIndex: number
  explanation?: string
}

export interface ConceptProgressState {
  questionText: string
  explanationHistory: string[]
  masteryAttempted: boolean
  regressed: boolean
  mastered: boolean
  hintLevel: number
}

// Student input classification

export type StudentInputClass = 'asks_question' | 'confused_or_stuck' | 'requests_hint' | 'normal'
export type QuestionSubClass = 'needs_clarification' | 'philosophical' | 'off_concept'
export type SupportStrategy = 'simplify' | 'analogise'

const HINT_REQUEST_PATTERNS = [/\bhint\b/i, /\bhint\b/i, /\bhelp\b/i, /\bclue\b/i, /\bstuck\b/i]

const PHILOSOPHICAL_PATTERNS = [
  /\bshould\b/i, /\bought\b/i,
  /\bfair\b/i, /\bjust\b/i, /\bmoral\b/i, /\bethic/i,
  /\bwhat.*point\b/i, /\bpurpose\b/i, /\bmeaning\b/i, /\bdoes.*matter\b/i,
  /\bmore\b.*\bthan\b/i,
]

const DEFINITIONAL_QUESTION_PATTERNS = [
  /^what (is|are|does|do)\b/i,
  /^which (of the following )?(best )?(defines?|describes?|refers? to|means?)\b/i,
  /^the term\b/i,
  /^how (is|are|would you define)\b/i,
  /\baccording to (mill|locke|rousseau|kant|aristotle|plato)\b.*\bwhat\b/i,
]

// Returns the appropriate concept-application follow-up for a correct MCQ answer.
// Definitional questions ("What is X?") get an application prompt instead of
// "explain why correct" — there's nothing to explain about a definition.
export function getConceptApplicationPrompt(questionText: string): string {
  const isDefinitional = DEFINITIONAL_QUESTION_PATTERNS.some(p => p.test(questionText.trim()))
  if (isDefinitional) {
    return 'Now that you know what it means, can you give an example of this idea in practice, or explain why it matters?'
  }
  return 'Explain why that answer is correct in your own words or expand on your answer.'
}

export function classifyStudentInput(text: string): StudentInputClass {
  if (HINT_REQUEST_PATTERNS.some(p => p.test(text))) return 'requests_hint'
  if (showsUncertainty(text)) return 'confused_or_stuck'
  if (isClarifyingQuestion(text)) return 'asks_question'
  return 'normal'
}

export function classifyQuestion(text: string, topicKeywords: string[]): QuestionSubClass {
  const lower = text.toLowerCase()
  if (PHILOSOPHICAL_PATTERNS.some(p => p.test(text))) return 'philosophical'
  const hasTopicWord = topicKeywords.some(kw => lower.includes(kw.toLowerCase()))
  if (!hasTopicWord) return 'off_concept'
  return 'needs_clarification'
}

export function detectSupportStrategy(text: string): SupportStrategy {
  const tokens = explanationTokens(text)
  // Short / fragmented responses → break into smaller steps
  if (tokens.size < 4) return 'simplify'
  return 'analogise'
}

// Re-exported so consumers don't need to reach into Chat.tsx for these.
export type { CitationData }
