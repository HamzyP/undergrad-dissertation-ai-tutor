import { describe, expect, it } from 'vitest'
import {
  classifyQuestion,
  classifyStudentInput,
  detectSupportStrategy,
  fallbackExplanationOutcome,
  getConceptApplicationPrompt,
} from './tutorUtils'

const LIBERALISM_KEYWORDS = ['liberal', 'liberty', 'freedom', 'rights', 'harm', 'autonomy', 'mill', 'state', 'individual']

describe('fallbackExplanationOutcome', () => {
  it('classifies a substantive causal explanation as correct', () => {
    expect(
      fallbackExplanationOutcome(
        'Because Mill limits coercion to cases where someone harms other people, the state cannot interfere just because it dislikes a choice.',
      ),
    ).toBe('correct')
  })

  it('classifies a thin but somewhat reasoned answer as partial', () => {
    expect(
      fallbackExplanationOutcome('Because harm matters.'),
    ).toBe('partial')
  })

  it('classifies uncertainty as incorrect', () => {
    expect(fallbackExplanationOutcome("I'm not sure, maybe because freedom is good?")).toBe('incorrect')
  })
})

describe('classifyStudentInput', () => {
  it('routes a hint request to requests_hint', () => {
    expect(classifyStudentInput('Can I get a hint?')).toBe('requests_hint')
  })

  it('routes a stuck/help message to requests_hint via the help/stuck pattern', () => {
    expect(classifyStudentInput("I'm stuck")).toBe('requests_hint')
  })

  it('routes uncertainty cues to confused_or_stuck', () => {
    expect(classifyStudentInput("I'm confused")).toBe('confused_or_stuck')
  })

  it('routes a clarifying question to asks_question', () => {
    expect(classifyStudentInput('What exactly counts as harm here?')).toBe('asks_question')
  })

  it('routes a reasoning explanation to normal', () => {
    expect(
      classifyStudentInput('Because Mill only allows coercion to prevent harm to others.'),
    ).toBe('normal')
  })
})

describe('classifyQuestion', () => {
  it('classifies a definitional/clarification question on a topic keyword as needs_clarification', () => {
    expect(classifyQuestion('What exactly counts as harm here?', LIBERALISM_KEYWORDS)).toBe(
      'needs_clarification',
    )
  })

  it('classifies a moral/value question as philosophical', () => {
    expect(
      classifyQuestion('Should Mill care more about dignity than harm?', LIBERALISM_KEYWORDS),
    ).toBe('philosophical')
  })

  it('classifies an off-topic question as off_concept', () => {
    expect(classifyQuestion('What would Rawls say instead?', LIBERALISM_KEYWORDS)).toBe('off_concept')
  })
})

describe('detectSupportStrategy', () => {
  it('returns simplify for short fragments', () => {
    expect(detectSupportStrategy('I am stuck')).toBe('simplify')
  })

  it('returns analogise when the message has more substantive tokens', () => {
    expect(
      detectSupportStrategy(
        "I don't know, I cannot figure out how Mill's limits on coercion actually work in practice.",
      ),
    ).toBe('analogise')
  })
})

describe('getConceptApplicationPrompt', () => {
  it('returns the application prompt for a definitional question', () => {
    expect(getConceptApplicationPrompt('What is the harm principle?')).toContain('example')
  })

  it('returns the explain-why prompt for a non-definitional question', () => {
    expect(
      getConceptApplicationPrompt(
        'Why does Mill restrict coercion to harm to others rather than offence?',
      ),
    ).toBe('Explain why that answer is correct in your own words or expand on your answer.')
  })
})
