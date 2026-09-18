import { useState } from 'react'
import type {
  ConsolidationState,
  ConceptProgressState,
  ConsolidationApiQuestion,
} from '../lib/tutorUtils'
import { logTutorConsoleError } from '../lib/tutorUtils'
import type { CitationData, ConsolidationQuestionData } from '../Chat'
import type { InterpolatedQuestion } from '../QuestionOverlay'

// Tracks where we are inside the remediation loop after a failed interpolated MCQ.
type RemediationStep =
  | { step: 'easy_mcq'; originalQuestion: InterpolatedQuestion; easyQuestion: ConsolidationApiQuestion; hint: string }
  | { step: 'intervention'; originalQuestion: InterpolatedQuestion; easyQuestion: ConsolidationApiQuestion; hint: string }
  | { step: 'post_intervention_mcq'; originalQuestion: InterpolatedQuestion; newQuestion: ConsolidationApiQuestion }

interface UseConsolidationOptions {
  topic: string
  model?: string
  addTextMessage: (sender: 'user' | 'tutor', text: string, citations?: CitationData[]) => void
  addConsolidationMessage: (data: ConsolidationQuestionData) => void
  addChoiceMessage: (text: string) => void
  addInterventionMessage: (text: string) => void
  updateScaffoldScore: (eventScore: number) => number
  playVideo: () => void
  seekVideo: (time: number) => void
  setFocusedConceptId: (id: number | null) => void
}

export function useConsolidation({
  topic,
  model,
  addTextMessage,
  addConsolidationMessage,
  addChoiceMessage,
  addInterventionMessage,
  updateScaffoldScore,
  playVideo,
  seekVideo,
  setFocusedConceptId,
}: UseConsolidationOptions) {
  const [consolidation, setConsolidation] = useState<ConsolidationState | null>(null)
  const [awaitingChoice, setAwaitingChoice] = useState(false)
  const [remediation, setRemediation] = useState<RemediationStep | null>(null)
  const [conceptProgress, setConceptProgress] = useState<Record<number, ConceptProgressState>>({})

  const getConceptState = (conceptId: number, questionText: string): ConceptProgressState =>
    conceptProgress[conceptId] ?? {
      questionText,
      explanationHistory: [],
      masteryAttempted: false,
      regressed: false,
      mastered: false,
      hintLevel: 0,
    }

  const updateConceptState = (
    conceptId: number,
    questionText: string,
    updater: (current: ConceptProgressState) => ConceptProgressState,
  ) => {
    setConceptProgress(prev => {
      const current = prev[conceptId] ?? {
        questionText,
        explanationHistory: [],
        masteryAttempted: false,
        regressed: false,
        mastered: false,
        hintLevel: 0,
      }
      return { ...prev, [conceptId]: updater(current) }
    })
  }

  const offerChoice = () => {
    setConsolidation(null)
    setAwaitingChoice(true)
    addChoiceMessage('Would you like to discuss this further, or continue watching the video?')
  }

  // ── Remediation flow ──────────────────────────────────────────────────────
  // Called when the student fails both attempts on an interpolated MCQ.
  // Fetches: explanation of the correct answer, an easier MCQ, and a hint.

  const startRemediation = async (failedQuestion: InterpolatedQuestion) => {
    try {
      const response = await fetch('http://127.0.0.1:8000/api/remediation/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          original_question: failedQuestion.question,
          correct_answer: failedQuestion.options[failedQuestion.correctIndex],
          topic,
          ...(model ? { model } : {}),
        }),
      })
      if (!response.ok) throw new Error(`Backend returned ${response.status}`)
      const data: { explanation: string; easy_question: ConsolidationApiQuestion | null; hint: string } =
        await response.json()

      addTextMessage('tutor', data.explanation)

      if (!data.easy_question) {
        logTutorConsoleError('REMEDIATION', 'Backend returned no easy question; offering choice.', {
          topic, failedQuestion: failedQuestion.question,
        })
        updateScaffoldScore(-1)
        offerChoice()
        return
      }

      setRemediation({
        step: 'easy_mcq',
        originalQuestion: failedQuestion,
        easyQuestion: data.easy_question,
        hint: data.hint,
      })
      addConsolidationMessage({
        question: data.easy_question.question,
        options: data.easy_question.options,
        correctIndex: data.easy_question.correct_index,
        citations: data.easy_question.citations,
      })
    } catch (error) {
      logTutorConsoleError('REMEDIATION', 'Failed to generate remediation content; offering choice.', {
        topic, failedQuestion: failedQuestion.question, error,
      })
      updateScaffoldScore(-2)
      addTextMessage('tutor', "That was a tricky one.")
      offerChoice()
    }
  }

  // Called when the student answers the easy remediation MCQ.
  const handleRemediationAnswer = (selectedIndex: number) => {
    if (!remediation || remediation.step !== 'easy_mcq') return

    const correct = selectedIndex === remediation.easyQuestion.correct_index

    if (correct) {
      const newScore = updateScaffoldScore(1)
      console.log(`Remediation easy MCQ: correct, score=${newScore.toFixed(2)}`)
      setRemediation(null)
      offerChoice()
    } else {
      // Move to intervention menu — student needs more help
      setRemediation({ ...remediation, step: 'intervention' })
      addInterventionMessage('How would you like to continue?')
    }
  }

  // Called when student picks Rewatch or Hint+Reword from the intervention menu.
  const handleInterventionChoice = (choice: 'rewatch' | 'hint') => {
    if (!remediation || remediation.step !== 'intervention') return

    if (choice === 'rewatch') {
      addTextMessage('tutor', 'Rewatching the relevant section — try the question again after.')
      seekVideo(remediation.originalQuestion.rewatchStart)
      playVideo()
      // The original interpolated MCQ will re-trigger naturally when the video
      // reaches the timestamp again (answeredIds does not include it yet).
      setRemediation(null)
      return
    }

    // hint: show the hint and re-present the same easy question — no LLM call needed
    addTextMessage('tutor', `Hint: ${remediation.hint}`)
    setRemediation({
      step: 'post_intervention_mcq',
      originalQuestion: remediation.originalQuestion,
      newQuestion: {
        question: remediation.easyQuestion.question,
        options: remediation.easyQuestion.options,
        correct_index: remediation.easyQuestion.correct_index,
        citations: remediation.easyQuestion.citations,
      },
    })
    addConsolidationMessage({
      question: remediation.easyQuestion.question,
      options: remediation.easyQuestion.options,
      correctIndex: remediation.easyQuestion.correct_index,
      citations: remediation.easyQuestion.citations,
    })
    return
  }

  // Called when the student answers the post-intervention reworded MCQ.
  const handlePostInterventionAnswer = (selectedIndex: number) => {
    if (!remediation || remediation.step !== 'post_intervention_mcq') return

    const correct = selectedIndex === remediation.newQuestion.correct_index

    if (correct) {
      const newScore = updateScaffoldScore(0.5)
      console.log(`Remediation post-intervention MCQ: correct, score=${newScore.toFixed(2)}`)
      setRemediation(null)
      offerChoice()
    } else {
      giveAnswerAndAdjustScaffold(remediation.originalQuestion)
    }
  }

  const giveAnswerAndAdjustScaffold = (originalQuestion: InterpolatedQuestion) => {
    const newScore = updateScaffoldScore(-1)
    console.log(`Remediation exhausted: giving answer, score=${newScore.toFixed(2)}`)
    setRemediation(null)
    addTextMessage(
      'tutor',
      `The correct answer was: ${originalQuestion.options[originalQuestion.correctIndex]}. We can revisit this concept.`,
    )
    offerChoice()
  }

  // ── Consolidation / Mastery flow ──────────────────────────────────────────

  const startConsolidation = async (
    conceptId: number,
    originalQuestion: string,
    studentExplanation: string,
    gapFocus?: string,
  ) => {
    try {
      const response = await fetch('http://127.0.0.1:8000/api/consolidation/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          original_question: originalQuestion,
          student_explanation: studentExplanation,
          ...(gapFocus ? { gap_focus: gapFocus } : {}),
          topic,
          ...(model ? { model } : {}),
        }),
      })
      if (!response.ok) throw new Error(`Backend returned ${response.status}`)
      const data: { questions: ConsolidationApiQuestion[] } = await response.json()

      if (data.questions.length >= 1) {
        setConsolidation({ kind: 'consolidation', conceptId, questions: data.questions, currentIndex: 0 })
        addConsolidationMessage({
          question: data.questions[0].question,
          options: data.questions[0].options,
          correctIndex: data.questions[0].correct_index,
          citations: data.questions[0].citations,
        })
      } else {
        logTutorConsoleError(
          'CONSOLIDATION',
          'Backend returned zero consolidation questions; falling back to choice prompt.',
          { topic, conceptId, originalQuestion, studentExplanation, gapFocus },
        )
        offerChoice()
      }
    } catch (error) {
      logTutorConsoleError('CONSOLIDATION', 'Failed to generate consolidation questions.', {
        topic, conceptId, originalQuestion, studentExplanation, gapFocus, error,
      })
      offerChoice()
    }
  }

  const startMasteryCheck = async (
    conceptId: number,
    originalQuestion: string,
    studentExplanation: string,
  ) => {
    updateConceptState(conceptId, originalQuestion, current => ({
      ...current,
      questionText: originalQuestion,
      masteryAttempted: true,
      regressed: false,
    }))

    try {
      const response = await fetch('http://127.0.0.1:8000/api/mastery/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          original_question: originalQuestion,
          student_explanation: studentExplanation,
          topic,
          ...(model ? { model } : {}),
        }),
      })
      if (!response.ok) throw new Error(`Backend returned ${response.status}`)
      const data: { question: ConsolidationApiQuestion | null } = await response.json()

      if (data.question) {
        addTextMessage('tutor', 'You seem to understand this idea. Try one quick mastery check before we move on.')
        setConsolidation({
          kind: 'mastery',
          conceptId,
          questions: [data.question],
          currentIndex: 0,
        })
        addConsolidationMessage({
          question: data.question.question,
          options: data.question.options,
          correctIndex: data.question.correct_index,
          citations: data.question.citations,
        })
        return
      }

      logTutorConsoleError('MASTERY', 'Backend returned no mastery question; auto-continuing.', {
        topic, conceptId, originalQuestion, studentExplanation,
      })
    } catch (error) {
      logTutorConsoleError('MASTERY', 'Failed to generate mastery question; auto-continuing.', {
        topic, conceptId, originalQuestion, studentExplanation, error,
      })
    }

    updateConceptState(conceptId, originalQuestion, current => ({
      ...current,
      questionText: originalQuestion,
      mastered: true,
      regressed: false,
    }))
    setFocusedConceptId(null)
    addTextMessage('tutor', "Your explanation shows solid understanding. Let's continue with the video.")
    playVideo()
  }

  const startDiscussionCheck = async (
    conceptId: number,
    originalQuestion: string,
    studentQuestion: string,
    questionClassification?: 'needs_clarification' | 'philosophical' | 'off_concept',
  ) => {
    try {
      const response = await fetch('http://127.0.0.1:8000/api/discussion-check/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          original_question: originalQuestion,
          student_question: studentQuestion,
          ...(questionClassification ? { question_classification: questionClassification } : {}),
          topic,
          ...(model ? { model } : {}),
        }),
      })
      if (!response.ok) throw new Error(`Backend returned ${response.status}`)
      const data: { question: ConsolidationApiQuestion | null; explanation: string } = await response.json()

      if (data.question) {
        setConsolidation({
          kind: 'discussion_check',
          conceptId,
          questions: [data.question],
          currentIndex: 0,
          explanation: data.explanation,
        })
        addConsolidationMessage({
          question: data.question.question,
          options: data.question.options,
          correctIndex: data.question.correct_index,
          citations: data.question.citations,
        })
        return
      }

      logTutorConsoleError('DISCUSSION_CHECK', 'Backend returned no discussion-check question; auto-continuing to choice prompt.', {
        topic, conceptId, originalQuestion, studentQuestion, questionClassification,
      })
    } catch (error) {
      logTutorConsoleError('DISCUSSION_CHECK', 'Failed to generate discussion-check question.', {
        topic, conceptId, originalQuestion, studentQuestion, questionClassification, error,
      })
    }

    offerChoice()
  }

  const handleConsolidationAnswer = (_messageId: number, selectedIndex: number) => {
    if (!consolidation) return

    const activeFollowUpQuestion = consolidation.questions[consolidation.currentIndex]
    const answeredCorrectly = selectedIndex === activeFollowUpQuestion.correct_index

    const letter = String.fromCharCode(65 + selectedIndex)
    const chosenText = activeFollowUpQuestion.options[selectedIndex]
    const outcomeTag = answeredCorrectly ? '✓' : '✗'
    addTextMessage('user', `[MCQ ANSWER] ${letter}) ${chosenText} ${outcomeTag}`)

    if (consolidation.kind === 'discussion_check') {
      setConsolidation(null)

      if (answeredCorrectly) {
        const newScore = updateScaffoldScore(0.5)
        console.log(`Discussion check ${consolidation.conceptId}: correct, score=${newScore.toFixed(2)}`)
        offerChoice()
      } else {
        const newScore = updateScaffoldScore(-0.5)
        console.log(`Discussion check ${consolidation.conceptId}: incorrect, score=${newScore.toFixed(2)}`)
        addTextMessage('tutor', consolidation.explanation ?? `The correct answer was: ${activeFollowUpQuestion.options[activeFollowUpQuestion.correct_index]}.`, activeFollowUpQuestion.citations)
        window.setTimeout(() => {
          offerChoice()
        }, 2000)
      }
      return
    }

    if (consolidation.kind === 'mastery') {
      const conceptQuestion = getConceptState(consolidation.conceptId, '').questionText
      setConsolidation(null)

      if (answeredCorrectly) {
        updateConceptState(consolidation.conceptId, conceptQuestion, current => ({
          ...current,
          questionText: conceptQuestion || current.questionText,
          mastered: true,
          regressed: false,
        }))
        setFocusedConceptId(null)
        addTextMessage('tutor', "That's right. You've mastered this concept, so let's continue with the video.")
        playVideo()
      } else {
        const newScore = updateScaffoldScore(-0.5)
        console.log(`Mastery check ${consolidation.conceptId}: incorrect, score=${newScore.toFixed(2)}`)
        updateConceptState(consolidation.conceptId, conceptQuestion, current => ({
          ...current,
          questionText: conceptQuestion || current.questionText,
          regressed: true,
          mastered: false,
        }))
        addTextMessage('tutor', "Not quite yet. Let's keep working through this idea together.")
        offerChoice()
      }
      return
    }

    const nextIndex = consolidation.currentIndex + 1
    if (nextIndex < consolidation.questions.length) {
      setConsolidation({ ...consolidation, currentIndex: nextIndex })
      addConsolidationMessage({
        question: consolidation.questions[nextIndex].question,
        options: consolidation.questions[nextIndex].options,
        correctIndex: consolidation.questions[nextIndex].correct_index,
        citations: consolidation.questions[nextIndex].citations,
      })
    } else {
      offerChoice()
    }
  }

  const handleChoice = (choice: 'discuss' | 'continue') => {
    setAwaitingChoice(false)
    if (choice === 'continue') {
      setFocusedConceptId(null)
      addTextMessage('tutor', "Great, let's continue with the video.")
      playVideo()
    } else {
      addTextMessage('tutor', "Sure, let's discuss. What would you like to explore?")
    }
  }

  return {
    consolidation,
    awaitingChoice,
    remediation,
    conceptProgress,
    getConceptState,
    updateConceptState,
    startConsolidation,
    startMasteryCheck,
    startDiscussionCheck,
    startRemediation,
    handleRemediationAnswer,
    handleInterventionChoice,
    handlePostInterventionAnswer,
    handleConsolidationAnswer,
    handleChoice,
  }
}
