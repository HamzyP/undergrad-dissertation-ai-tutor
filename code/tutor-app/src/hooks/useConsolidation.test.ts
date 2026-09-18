import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { useConsolidation } from './useConsolidation'
import type { InterpolatedQuestion } from '../QuestionOverlay'

const FAILED_QUESTION: InterpolatedQuestion = {
  id: 7,
  timestamp: 100,
  question: 'What is the harm principle?',
  options: ['Liberty limit by harm to others', 'Maximise virtue', 'Punish offence', 'Empower the state'],
  correctIndex: 0,
  rewatchStart: 80,
}

const VALID_EASY_QUESTION = {
  question: 'According to Mill, when may the state interfere with liberty?',
  options: ['When it prevents harm to others', 'Whenever it disagrees', 'To enforce virtue', 'Never'],
  correct_index: 0,
  citations: [],
}

function setupConsolidation() {
  const addTextMessage = vi.fn()
  const addConsolidationMessage = vi.fn()
  const addChoiceMessage = vi.fn()
  const addInterventionMessage = vi.fn()
  const updateScaffoldScore = vi.fn().mockReturnValue(0)
  const playVideo = vi.fn()
  const seekVideo = vi.fn()
  const setFocusedConceptId = vi.fn()

  const hook = renderHook(() =>
    useConsolidation({
      topic: 'liberalism',
      addTextMessage,
      addConsolidationMessage,
      addChoiceMessage,
      addInterventionMessage,
      updateScaffoldScore,
      playVideo,
      seekVideo,
      setFocusedConceptId,
    }),
  )

  return { hook, addTextMessage, addConsolidationMessage, addChoiceMessage, addInterventionMessage, playVideo, seekVideo }
}

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('useConsolidation.startRemediation — fallback paths', () => {
  it('offers the choice prompt when the backend returns easy_question: null', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        json: async () => ({ explanation: 'The correct answer is X.', easy_question: null, hint: '' }),
      })),
    )
    const { hook, addChoiceMessage, addConsolidationMessage, playVideo } = setupConsolidation()

    await act(async () => {
      await hook.result.current.startRemediation(FAILED_QUESTION)
    })

    expect(addChoiceMessage).toHaveBeenCalledTimes(1)
    expect(addConsolidationMessage).not.toHaveBeenCalled()
    expect(playVideo).not.toHaveBeenCalled()
    expect(hook.result.current.awaitingChoice).toBe(true)
  })

  it('offers the choice prompt when the remediation API call fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('network') }))
    const { hook, addChoiceMessage, playVideo } = setupConsolidation()

    await act(async () => {
      await hook.result.current.startRemediation(FAILED_QUESTION)
    })

    expect(addChoiceMessage).toHaveBeenCalledTimes(1)
    expect(playVideo).not.toHaveBeenCalled()
    expect(hook.result.current.awaitingChoice).toBe(true)
  })

  it('shows the easy MCQ when the backend returns a valid easy_question', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        json: async () => ({
          explanation: 'Mill limits state coercion to harm prevention.',
          easy_question: VALID_EASY_QUESTION,
          hint: 'Think about who is affected.',
        }),
      })),
    )
    const { hook, addConsolidationMessage, addChoiceMessage } = setupConsolidation()

    await act(async () => {
      await hook.result.current.startRemediation(FAILED_QUESTION)
    })

    expect(addConsolidationMessage).toHaveBeenCalledTimes(1)
    expect(addChoiceMessage).not.toHaveBeenCalled()
    expect(hook.result.current.remediation?.step).toBe('easy_mcq')
  })
})

describe('useConsolidation.handleInterventionChoice — hint path', () => {
  it('shows the hint and re-presents the same easy question without an LLM call', async () => {
    const fetchSpy = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        explanation: 'Mill limits state coercion.',
        easy_question: VALID_EASY_QUESTION,
        hint: 'Hint text',
      }),
    }))
    vi.stubGlobal('fetch', fetchSpy)

    const { hook, addTextMessage, addConsolidationMessage } = setupConsolidation()

    await act(async () => {
      await hook.result.current.startRemediation(FAILED_QUESTION)
    })
    act(() => {
      hook.result.current.handleRemediationAnswer(1)
    })
    expect(hook.result.current.remediation?.step).toBe('intervention')

    fetchSpy.mockClear()

    act(() => {
      hook.result.current.handleInterventionChoice('hint')
    })

    expect(fetchSpy).not.toHaveBeenCalled()
    expect(addTextMessage).toHaveBeenCalledWith('tutor', 'Hint: Hint text')
    expect(addConsolidationMessage).toHaveBeenCalledWith(expect.objectContaining({
      question: VALID_EASY_QUESTION.question,
      options: VALID_EASY_QUESTION.options,
      correctIndex: VALID_EASY_QUESTION.correct_index,
    }))
    expect(hook.result.current.remediation?.step).toBe('post_intervention_mcq')
  })
})

describe('useConsolidation.handleConsolidationAnswer — mastery wrong path', () => {
  it('offers the choice prompt after a wrong mastery answer instead of hanging', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        json: async () => ({ question: VALID_EASY_QUESTION }),
      })),
    )
    const { hook, addChoiceMessage, playVideo } = setupConsolidation()

    await act(async () => {
      await hook.result.current.startMasteryCheck(1, 'What is the harm principle?', 'A reasoned explanation.')
    })
    expect(hook.result.current.consolidation?.kind).toBe('mastery')

    // Pick wrong index
    act(() => {
      hook.result.current.handleConsolidationAnswer(0, 1)
    })

    expect(addChoiceMessage).toHaveBeenCalledTimes(1)
    expect(playVideo).not.toHaveBeenCalled()
    expect(hook.result.current.awaitingChoice).toBe(true)
  })

  it('plays the video after a correct mastery answer', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        json: async () => ({ question: VALID_EASY_QUESTION }),
      })),
    )
    const { hook, addChoiceMessage, playVideo } = setupConsolidation()

    await act(async () => {
      await hook.result.current.startMasteryCheck(1, 'What is the harm principle?', 'A reasoned explanation.')
    })

    act(() => {
      hook.result.current.handleConsolidationAnswer(0, VALID_EASY_QUESTION.correct_index)
    })

    expect(playVideo).toHaveBeenCalledTimes(1)
    expect(addChoiceMessage).not.toHaveBeenCalled()
  })
})
