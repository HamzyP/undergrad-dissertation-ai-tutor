import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import type { InterpolatedQuestion } from '../QuestionOverlay'

// We mock the two collaborator hooks so the controller's routing logic is the
// only thing under test. Each mock exposes vi.fn() spies for the calls we
// care about, plus stable defaults for the rest of the surface area.

const tutorChatMock = vi.hoisted(() => {
  const requestTutorReply = vi.fn().mockResolvedValue(null)
  const addTextMessage = vi.fn()
  const addConsolidationMessage = vi.fn()
  const addChoiceMessage = vi.fn()
  const addInterventionMessage = vi.fn()
  return {
    requestTutorReply,
    addTextMessage,
    addConsolidationMessage,
    addChoiceMessage,
    addInterventionMessage,
    factory: () => ({
      messages: [],
      isTutorLoading: false,
      addTextMessage,
      addConsolidationMessage,
      addChoiceMessage,
      addInterventionMessage,
      requestTutorReply,
      nextMessageId: () => 0,
    }),
  }
})

const consolidationMock = vi.hoisted(() => {
  const startDiscussionCheck = vi.fn().mockResolvedValue(undefined)
  const startConsolidation = vi.fn().mockResolvedValue(undefined)
  const startMasteryCheck = vi.fn().mockResolvedValue(undefined)
  const startRemediation = vi.fn().mockResolvedValue(undefined)
  return {
    startDiscussionCheck,
    startConsolidation,
    startMasteryCheck,
    startRemediation,
    factory: () => ({
      consolidation: null,
      awaitingChoice: false,
      remediation: null,
      getConceptState: () => ({
        questionText: '',
        explanationHistory: [],
        masteryAttempted: false,
        regressed: false,
        mastered: false,
        hintLevel: 0,
      }),
      updateConceptState: vi.fn(),
      startDiscussionCheck,
      startConsolidation,
      startMasteryCheck,
      startRemediation,
      handleConsolidationAnswer: vi.fn(),
      handleChoice: vi.fn(),
      handleRemediationAnswer: vi.fn(),
      handleInterventionChoice: vi.fn(),
      handlePostInterventionAnswer: vi.fn(),
    }),
  }
})

vi.mock('./useTutorChat', () => ({
  useTutorChat: () => tutorChatMock.factory(),
}))

vi.mock('./useConsolidation', () => ({
  useConsolidation: () => consolidationMock.factory(),
}))

// Imported AFTER the mocks so the hook picks up the mocked collaborators.
import { useTutorController } from './useTutorController'

const QUESTION: InterpolatedQuestion = {
  id: 1,
  timestamp: 60,
  rewatchStart: 55,
  question: 'According to Mill, what is the main principle that should guide restrictions on individual liberties?',
  options: [
    'Preventing harm to others',
    'Maximising state power',
    'Enforcing virtue',
    'Punishing offence',
  ],
  correctIndex: 0,
}

function renderController() {
  return renderHook(() =>
    useTutorController({
      topic: 'liberalism',
      initialScore: 0,
      interpolatedQuestions: [QUESTION],
      currentTime: 60,
      playVideo: vi.fn(),
      seekVideo: vi.fn(),
    }),
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  // Stub the explanation evaluation HTTP call so we can drive outcomes from tests.
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({
      ok: true,
      json: async () => ({ outcome: 'partial', gap_focus: 'missing harm-to-others distinction' }),
    })),
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('useTutorController.handleSend — pendingExplanation branch', () => {
  it('routes a reasoning explanation through evaluateExplanation and into consolidation when partial', async () => {
    const { result } = renderController()
    act(() => result.current.handleAnswer(true, 1, 0, QUESTION))
    expect(result.current.pendingExplanation).not.toBeNull()

    await act(async () => {
      await result.current.handleSend('Because Mill only allows coercion to prevent harm to others.')
    })

    // Explanation evaluation HTTP was called.
    expect(fetch).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/api/explanation/evaluate',
      expect.any(Object),
    )
    // Tutor reply received the partial outcome metadata.
    expect(tutorChatMock.requestTutorReply).toHaveBeenCalledWith(
      expect.objectContaining({ explanationOutcome: 'partial' }),
    )
    // Closing MCQ converged on consolidation, not mastery.
    expect(consolidationMock.startConsolidation).toHaveBeenCalledTimes(1)
    expect(consolidationMock.startMasteryCheck).not.toHaveBeenCalled()
    expect(consolidationMock.startDiscussionCheck).not.toHaveBeenCalled()
  })

  it('routes a correct explanation into the mastery check', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        json: async () => ({ outcome: 'correct', gap_focus: '' }),
      })),
    )
    const { result } = renderController()
    act(() => result.current.handleAnswer(true, 1, 0, QUESTION))

    await act(async () => {
      await result.current.handleSend(
        'Because Mill limits coercion to cases where someone harms other people, the state cannot interfere just because it dislikes a choice.',
      )
    })

    expect(consolidationMock.startMasteryCheck).toHaveBeenCalledTimes(1)
    expect(consolidationMock.startConsolidation).not.toHaveBeenCalled()
    expect(consolidationMock.startDiscussionCheck).not.toHaveBeenCalled()
  })

  it('does NOT trigger mastery when explanation is incorrect (conflation guard)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        json: async () => ({ outcome: 'incorrect', gap_focus: 'confuses harm with offence' }),
      })),
    )
    const { result } = renderController()
    act(() => result.current.handleAnswer(true, 1, 0, QUESTION))

    await act(async () => {
      await result.current.handleSend('Harm and offence are basically the same because both upset people.')
    })

    expect(consolidationMock.startMasteryCheck).not.toHaveBeenCalled()
    expect(consolidationMock.startConsolidation).toHaveBeenCalledTimes(1)
    expect(tutorChatMock.requestTutorReply).toHaveBeenCalledWith(
      expect.objectContaining({ explanationOutcome: 'incorrect' }),
    )
  })

  it('skips explanation evaluation and routes a clarifying question to discussion-check', async () => {
    const { result } = renderController()
    act(() => result.current.handleAnswer(true, 1, 0, QUESTION))

    await act(async () => {
      await result.current.handleSend('What exactly counts as harm here?')
    })

    expect(fetch).not.toHaveBeenCalled()
    expect(consolidationMock.startDiscussionCheck).toHaveBeenCalledWith(
      QUESTION.id,
      QUESTION.question,
      'What exactly counts as harm here?',
      'needs_clarification',
    )
    // Reply forwarded the question classification, not an explanation outcome.
    expect(tutorChatMock.requestTutorReply).toHaveBeenCalledWith(
      expect.objectContaining({
        questionClassification: 'needs_clarification',
        explanationOutcome: undefined,
      }),
    )
    expect(consolidationMock.startConsolidation).not.toHaveBeenCalled()
    expect(consolidationMock.startMasteryCheck).not.toHaveBeenCalled()
  })

  it('routes a philosophical question to discussion-check with philosophical classification', async () => {
    const { result } = renderController()
    act(() => result.current.handleAnswer(true, 1, 0, QUESTION))

    await act(async () => {
      await result.current.handleSend('Should Mill care more about dignity than harm?')
    })

    expect(fetch).not.toHaveBeenCalled()
    expect(consolidationMock.startDiscussionCheck).toHaveBeenCalledWith(
      QUESTION.id,
      QUESTION.question,
      'Should Mill care more about dignity than harm?',
      'philosophical',
    )
    expect(tutorChatMock.requestTutorReply).toHaveBeenCalledWith(
      expect.objectContaining({
        questionClassification: 'philosophical',
        explanationOutcome: undefined,
      }),
    )
  })

  it('routes an off-concept question to discussion-check with off_concept classification', async () => {
    const { result } = renderController()
    act(() => result.current.handleAnswer(true, 1, 0, QUESTION))

    await act(async () => {
      await result.current.handleSend('What would Rawls say instead?')
    })

    expect(fetch).not.toHaveBeenCalled()
    expect(consolidationMock.startDiscussionCheck).toHaveBeenCalledWith(
      QUESTION.id,
      QUESTION.question,
      'What would Rawls say instead?',
      'off_concept',
    )
    expect(tutorChatMock.requestTutorReply).toHaveBeenCalledWith(
      expect.objectContaining({
        questionClassification: 'off_concept',
        explanationOutcome: undefined,
      }),
    )
  })

  it('routes a short confused message with simplify strategy to discussion-check', async () => {
    const { result } = renderController()
    act(() => result.current.handleAnswer(true, 1, 0, QUESTION))

    await act(async () => {
      await result.current.handleSend("I'm confused")
    })

    expect(fetch).not.toHaveBeenCalled()
    expect(consolidationMock.startDiscussionCheck).toHaveBeenCalledTimes(1)
    expect(tutorChatMock.requestTutorReply).toHaveBeenCalledWith(
      expect.objectContaining({
        supportStrategy: 'simplify',
        explanationOutcome: undefined,
      }),
    )
  })

  it('routes a longer stuck message with analogise strategy to discussion-check', async () => {
    const { result } = renderController()
    act(() => result.current.handleAnswer(true, 1, 0, QUESTION))

    // Needs enough substantive tokens for analogise AND an uncertainty cue for
    // classifyStudentInput to route it as confused_or_stuck rather than normal.
    await act(async () => {
      await result.current.handleSend(
        "I don't know, I cannot figure out how Mill's limits on coercion actually work in practice.",
      )
    })

    expect(fetch).not.toHaveBeenCalled()
    expect(consolidationMock.startDiscussionCheck).toHaveBeenCalledTimes(1)
    expect(tutorChatMock.requestTutorReply).toHaveBeenCalledWith(
      expect.objectContaining({
        supportStrategy: 'analogise',
        explanationOutcome: undefined,
      }),
    )
  })

  it('routes a hint request with hintLevel through to requestTutorReply and discussion-check', async () => {
    const { result } = renderController()
    act(() => result.current.handleAnswer(true, 1, 0, QUESTION))

    await act(async () => {
      await result.current.handleSend('Can I get a hint?')
    })

    expect(fetch).not.toHaveBeenCalled()
    expect(consolidationMock.startDiscussionCheck).toHaveBeenCalledTimes(1)
    expect(tutorChatMock.requestTutorReply).toHaveBeenCalledWith(
      expect.objectContaining({
        hintLevel: expect.any(Number),
        explanationOutcome: undefined,
      }),
    )
  })

  it('asserts the tutor reply receives explanationOutcome correct for a correct explanation', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        json: async () => ({ outcome: 'correct', gap_focus: '' }),
      })),
    )
    const { result } = renderController()
    act(() => result.current.handleAnswer(true, 1, 0, QUESTION))

    await act(async () => {
      await result.current.handleSend(
        'Because Mill limits coercion to cases where someone harms other people, the state cannot interfere just because it dislikes a choice.',
      )
    })

    expect(tutorChatMock.requestTutorReply).toHaveBeenCalledWith(
      expect.objectContaining({ explanationOutcome: 'correct' }),
    )
  })
})

describe('useTutorController.handleSend — focused-concept branch (no pendingExplanation)', () => {
  it('routes a question intent through discussion-check when a focused concept exists', async () => {
    const { result } = renderController()
    // handleAnswer sets focusedConceptId AND pendingExplanation. Send a normal
    // explanation first to clear pendingExplanation while keeping focus.
    act(() => result.current.handleAnswer(true, 1, 0, QUESTION))
    await act(async () => {
      await result.current.handleSend(
        'Because Mill limits coercion to cases where someone harms other people.',
      )
    })
    vi.clearAllMocks()

    // Now we are in the focused-concept branch. A clarifying question must
    // still converge on a discussion-check closing MCQ.
    await act(async () => {
      await result.current.handleSend('What exactly counts as harm here?')
    })

    expect(consolidationMock.startDiscussionCheck).toHaveBeenCalledTimes(1)
    expect(consolidationMock.startConsolidation).not.toHaveBeenCalled()
    expect(consolidationMock.startMasteryCheck).not.toHaveBeenCalled()
  })
})
