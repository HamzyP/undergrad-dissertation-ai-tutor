import { useRef, useState } from 'react'
import type { InterpolatedQuestion } from '../QuestionOverlay'
import { useTutorChat } from './useTutorChat'
import { useConsolidation } from './useConsolidation'
import {
  scoreToLevel,
  levelLabels,
  isAcceptableReasoning,
  explanationsOverlap,
  fallbackExplanationOutcome,
  logTutorConsoleError,
  classifyStudentInput,
  classifyQuestion,
  detectSupportStrategy,
  getConceptApplicationPrompt,
} from '../lib/tutorUtils'
import type { ExplanationOutcome, PendingExplanation, QuestionSubClass, SupportStrategy } from '../lib/tutorUtils'

const TOPIC_KEYWORDS: Record<string, string[]> = {
  liberalism: ['liberal', 'liberty', 'freedom', 'rights', 'harm', 'autonomy', 'mill', 'state', 'individual'],
  'rep-democracy': ['democracy', 'representative', 'election', 'vote', 'parliament', 'government', 'citizen', 'accountability'],
}

interface UseTutorControllerOptions {
  topic: 'liberalism' | 'rep-democracy'
  model?: string
  initialScore: number
  interpolatedQuestions: InterpolatedQuestion[]
  currentTime: number
  playVideo: () => void
  seekVideo: (time: number) => void
}

interface ExplanationEvaluationResponse {
  outcome: ExplanationOutcome
  gap_focus?: string
}

type StudentIntent =
  | { kind: 'evaluate_response' }
  | { kind: 'classify_question'; questionClassification: QuestionSubClass }
  | { kind: 'support_strategy'; supportStrategy?: SupportStrategy; hintLevel?: number }

export function useTutorController({
  topic,
  model,
  initialScore,
  interpolatedQuestions,
  currentTime,
  playVideo,
  seekVideo,
}: UseTutorControllerOptions) {
  const [scaffoldScore, setScaffoldScore] = useState(initialScore)
  const [pendingExplanation, setPendingExplanation] = useState<PendingExplanation | null>(null)
  const [focusedConceptId, setFocusedConceptId] = useState<number | null>(null)

  const sessionIdRef = useRef(`session-${Math.random().toString(36).slice(2, 10)}`)
  const sendInFlightRef = useRef(false)

  const { messages, isTutorLoading, addTextMessage, addConsolidationMessage, addChoiceMessage, addInterventionMessage, requestTutorReply, getMessageTimestamp } =
    useTutorChat()

  const updateScaffoldScore = (eventScore: number) => {
    const newScore = scaffoldScore * 0.5 + eventScore * 0.5
    setScaffoldScore(newScore)
    return newScore
  }

  const consolidation = useConsolidation({
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
  })

  const currentLevel = scoreToLevel(scaffoldScore)

  const explanationScoreFor = (outcome: ExplanationOutcome, attempts: number): number => {
    if (outcome === 'correct') return attempts === 1 ? 4 : 2.5
    if (outcome === 'partial') return attempts === 1 ? 1.5 : 1
    return attempts === 1 ? -0.5 : -1
  }

  const evaluateExplanationOutcome = async (
    questionText: string,
    correctAnswer: string,
    studentExplanation: string,
  ): Promise<ExplanationEvaluationResponse> => {
    try {
      const response = await fetch('http://127.0.0.1:8000/api/explanation/evaluate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          original_question: questionText,
          correct_answer: correctAnswer,
          student_explanation: studentExplanation,
          topic,
          ...(model ? { model } : {}),
        }),
      })
      if (!response.ok) throw new Error(`Backend returned ${response.status}`)
      const data: ExplanationEvaluationResponse = await response.json()
      return data
    } catch (error) {
      logTutorConsoleError('EXPLANATION_EVAL', 'Falling back to local explanation evaluation.', {
        topic,
        questionText,
        correctAnswer,
        studentExplanation,
        error,
      })
      return {
        outcome: fallbackExplanationOutcome(studentExplanation),
      }
    }
  }

  const shouldTriggerMastery = (conceptId: number, questionText: string, explanation: string): boolean => {
    const state = consolidation.getConceptState(conceptId, questionText)
    if (state.mastered) return false
    if (state.masteryAttempted && !state.regressed) return false
    return !state.explanationHistory.some(previous => explanationsOverlap(previous, explanation))
  }

  const findQuestionById = (questionId: number | null | undefined) =>
    typeof questionId === 'number' ? interpolatedQuestions.find(q => q.id === questionId) : undefined

  const classifyStudentIntent = async (
    text: string,
    interpolatedQuestion?: string,
  ): Promise<StudentIntent> => {
    const inputClass = classifyStudentInput(text)
    const topicKeywords = TOPIC_KEYWORDS[topic] ?? []

    if (inputClass === 'asks_question') {
      return {
        kind: 'classify_question',
        questionClassification: classifyQuestion(text, topicKeywords),
      }
    }

    if (inputClass === 'confused_or_stuck') {
      return {
        kind: 'support_strategy',
        supportStrategy: detectSupportStrategy(text),
      }
    }

    if (inputClass === 'requests_hint' && focusedConceptId !== null) {
      const conceptState = consolidation.getConceptState(focusedConceptId, '')
      const nextHintLevel = Math.min((conceptState.hintLevel ?? 0) + 1, 3)
      consolidation.updateConceptState(focusedConceptId, conceptState.questionText, current => ({
        ...current,
        hintLevel: nextHintLevel,
      }))
      return {
        kind: 'support_strategy',
        hintLevel: nextHintLevel,
      }
    }

    // Regex returned 'normal' but the message has no reasoning cues — ambiguous.
    // Ask the LLM to break the tie before routing.
    if (!isAcceptableReasoning(text)) {
      try {
        const response = await fetch('http://127.0.0.1:8000/api/intent/classify', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: text,
            topic,
            ...(interpolatedQuestion ? { interpolated_question: interpolatedQuestion } : {}),
            ...(model ? { model } : {}),
          }),
        })
        if (response.ok) {
          const data: { intent: string } = await response.json()
          if (data.intent === 'asks_question') {
            return {
              kind: 'classify_question',
              questionClassification: classifyQuestion(text, topicKeywords),
            }
          }
          if (data.intent === 'confused_or_stuck') {
            return {
              kind: 'support_strategy',
              supportStrategy: detectSupportStrategy(text),
            }
          }
        }
      } catch (error) {
        logTutorConsoleError('INTENT_CLASSIFY', 'LLM intent classification failed; defaulting to evaluate_response.', { topic, text, error })
      }
    }

    return { kind: 'evaluate_response' }
  }

  // All routed tutor actions converge on a closing MCQ. We use discussion checks
  // for question/support branches, consolidation for weak explanations, and
  // mastery for strong explanations.
  const runClosingMcqForQuestionLikeTurn = async (
    question: InterpolatedQuestion,
    studentTurn: string,
    questionClassification?: QuestionSubClass,
  ) => {
    await consolidation.startDiscussionCheck(
      question.id,
      question.question,
      studentTurn,
      questionClassification,
    )
  }

  const runClosingMcqForEvaluatedResponse = async (
    question: InterpolatedQuestion,
    studentExplanation: string,
    explanationOutcome: ExplanationOutcome,
    explanationGap?: string,
  ) => {
    if (explanationOutcome === 'correct') {
      await consolidation.startMasteryCheck(question.id, question.question, studentExplanation)
      return
    }

    await consolidation.startConsolidation(
      question.id,
      question.question,
      studentExplanation,
      explanationGap,
    )
  }

  const sendTutorReplyForActiveQuestion = async ({
    text,
    scaffoldLevel,
    timestamp,
    historySnapshot,
    question,
    questionClassification,
    supportStrategy,
    hintLevel,
    explanationAttempt,
    explanationOutcome,
    explanationGap,
  }: {
    text: string
    scaffoldLevel: string
    timestamp: number
    historySnapshot: typeof messages
    question: InterpolatedQuestion
    questionClassification?: QuestionSubClass
    supportStrategy?: SupportStrategy
    hintLevel?: number
    explanationAttempt?: number
    explanationOutcome?: ExplanationOutcome
    explanationGap?: string
  }) => {
    await requestTutorReply({
      message: text,
      scaffoldLevel,
      timestamp,
      history: historySnapshot,
      topic,
      sessionId: sessionIdRef.current,
      model,
      interpolatedQuestion: question.question,
      interpolatedAnswerCorrect: true,
      explanationAttempt,
      explanationOutcome,
      explanationGap,
      questionClassification,
      supportStrategy,
      hintLevel,
    })
  }

  const handleQuestionOrSupportTurn = async ({
    text,
    scaffoldLevel,
    timestamp,
    historySnapshot,
    question,
    intent,
    explanationAttempt,
  }: {
    text: string
    scaffoldLevel: string
    timestamp: number
    historySnapshot: typeof messages
    question: InterpolatedQuestion
    intent: Extract<StudentIntent, { kind: 'classify_question' | 'support_strategy' }>
    explanationAttempt?: number
  }) => {
    const questionClassification =
      intent.kind === 'classify_question' ? intent.questionClassification : undefined
    const supportStrategy =
      intent.kind === 'support_strategy' ? intent.supportStrategy : undefined
    const hintLevel =
      intent.kind === 'support_strategy' ? intent.hintLevel : undefined

    await sendTutorReplyForActiveQuestion({
      text,
      scaffoldLevel,
      timestamp,
      historySnapshot,
      question,
      questionClassification,
      supportStrategy,
      hintLevel,
      explanationAttempt,
    })
    await runClosingMcqForQuestionLikeTurn(question, text, questionClassification)
  }

  const handleEvaluatedResponseTurn = async ({
    text,
    scaffoldLevel,
    timestamp,
    historySnapshot,
    question,
    previousPromptAttempts,
  }: {
    text: string
    scaffoldLevel: string
    timestamp: number
    historySnapshot: typeof messages
    question: InterpolatedQuestion
    previousPromptAttempts: number
  }) => {
    const attempts = previousPromptAttempts + 1
    const evaluation = await evaluateExplanationOutcome(
      question.question,
      question.options[question.correctIndex],
      text,
    )
    const explanationOutcome = evaluation.outcome
    const explanationGap = evaluation.gap_focus
    const eventScore = explanationScoreFor(explanationOutcome, attempts)
    const newScore = updateScaffoldScore(eventScore)
    console.log(
      `Question ${question.id}: attempts=${attempts}, outcome=${explanationOutcome}, eventScore=${eventScore}, newScore=${newScore.toFixed(2)}`,
    )

    consolidation.updateConceptState(question.id, question.question, current => ({
      ...current,
      questionText: question.question,
      explanationHistory: [...current.explanationHistory, text],
      regressed: explanationOutcome !== 'correct',
    }))

    await sendTutorReplyForActiveQuestion({
      text,
      scaffoldLevel,
      timestamp,
      historySnapshot,
      question,
      explanationAttempt: attempts,
      explanationOutcome,
      explanationGap,
    })
    await runClosingMcqForEvaluatedResponse(question, text, explanationOutcome, explanationGap)
  }

  const handleReword = async (question: InterpolatedQuestion): Promise<InterpolatedQuestion | null> => {
    const scaffoldLevel = levelLabels[currentLevel]
    try {
      const response = await fetch('http://127.0.0.1:8000/api/interpolated/reword', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          original_question: question.question,
          original_options: question.options,
          correct_index: question.correctIndex,
          scaffold_level: scaffoldLevel,
          topic,
          ...(model ? { model } : {}),
        }),
      })
      if (!response.ok) throw new Error(`Backend returned ${response.status}`)
      const data: { question: { question: string; options: string[]; correct_index: number } | null } = await response.json()
      if (!data.question) return null
      updateScaffoldScore(0.5)
      return {
        ...question,
        question: data.question.question,
        options: data.question.options,
        correctIndex: data.question.correct_index,
      }
    } catch (error) {
      logTutorConsoleError('INTERPOLATED_REWORD', 'Failed to reword interpolated question.', { topic, error })
      return null
    }
  }

  const handleHint = async (question: InterpolatedQuestion) => {
    const conceptState = consolidation.getConceptState(question.id, question.question)
    const nextHintLevel = Math.min((conceptState.hintLevel ?? 0) + 1, 3)
    consolidation.updateConceptState(question.id, question.question, current => ({
      ...current,
      hintLevel: nextHintLevel,
    }))
    updateScaffoldScore(-0.3)

    const scaffoldLevel = levelLabels[currentLevel]
    const timestamp = Math.floor(currentTime)
    const historySnapshot = [...messages]

    await requestTutorReply({
      message: 'Can I have a hint?',
      scaffoldLevel,
      timestamp,
      history: historySnapshot,
      topic,
      sessionId: sessionIdRef.current,
      model,
      interpolatedQuestion: question.question,
      hintLevel: nextHintLevel,
    })
  }

  const handleAnswer = (
    correct: boolean,
    attempts: number,
    selectedOption: number,
    question: InterpolatedQuestion,
  ) => {
    if (correct) {
      setPendingExplanation({ questionId: question.id, attempts })
      consolidation.updateConceptState(question.id, question.question, current => ({
        ...current,
        questionText: question.question,
      }))
      setFocusedConceptId(question.id)
      const followUp = getConceptApplicationPrompt(question.question)
      addTextMessage(
        'tutor',
        `Q: ${question.question}\nYour answer: ${question.options[selectedOption]}\n\n${followUp}`,
      )
    } else {
      addTextMessage(
        'tutor',
        `Q: ${question.question}\nYour incorrect answer: ${question.options[selectedOption]}\n\nLet's work through this together.`,
      )
      consolidation.startRemediation(question)
    }
  }

  const handleSend = async (text: string) => {
    console.debug('[controller] handleSend called', { text, sendInFlight: sendInFlightRef.current, pendingExplanation, focusedConceptId })
    if (sendInFlightRef.current) {
      logTutorConsoleError('CHAT_SEND', 'Ignored duplicate chat submission while a previous send was still being processed.', { topic, text })
      return
    }

    sendInFlightRef.current = true
    addTextMessage('user', text)

    try {
      const scaffoldLevel = levelLabels[currentLevel]
      const timestamp = Math.floor(currentTime)
      const historySnapshot = [...messages, { id: -1, sender: 'user' as const, type: 'text' as const, text }]
      const activeQuestion = pendingExplanation
        ? findQuestionById(pendingExplanation.questionId)
        : findQuestionById(focusedConceptId)
      const intent = await classifyStudentIntent(text, activeQuestion?.question)

      console.debug('[controller] routing send', { scaffoldLevel, timestamp, intent: intent.kind, branch: pendingExplanation ? 'pendingExplanation' : 'normal' })

      if (pendingExplanation) {
        const { attempts: previousPromptAttempts, questionId } = pendingExplanation
        const question = findQuestionById(questionId)

        if (!question) {
          setPendingExplanation(null)
          await requestTutorReply({
            message: text,
            scaffoldLevel,
            timestamp,
            history: historySnapshot,
            topic,
            sessionId: sessionIdRef.current,
            model,
            questionClassification: intent.kind === 'classify_question' ? intent.questionClassification : undefined,
            supportStrategy: intent.kind === 'support_strategy' ? intent.supportStrategy : undefined,
            hintLevel: intent.kind === 'support_strategy' ? intent.hintLevel : undefined,
          })
          return
        }

        if (intent.kind !== 'evaluate_response') {
          await handleQuestionOrSupportTurn({
            text,
            scaffoldLevel,
            timestamp,
            historySnapshot,
            question,
            intent,
            explanationAttempt: previousPromptAttempts + 1,
          })
          setPendingExplanation(null)
          return
        }

        await handleEvaluatedResponseTurn({
          text,
          scaffoldLevel,
          timestamp,
          historySnapshot,
          question,
          previousPromptAttempts,
        })
        setPendingExplanation(null)
      } else {
        const focusedQuestion = findQuestionById(focusedConceptId)

        // Main decision branch: question and support paths converge on a closing MCQ.
        if (focusedQuestion && intent.kind !== 'evaluate_response') {
          await handleQuestionOrSupportTurn({
            text,
            scaffoldLevel,
            timestamp,
            historySnapshot,
            question: focusedQuestion,
            intent,
          })
          return
        }

        await requestTutorReply({
          message: text,
          scaffoldLevel,
          timestamp,
          history: historySnapshot,
          topic,
          sessionId: sessionIdRef.current,
          model,
          questionClassification: intent.kind === 'classify_question' ? intent.questionClassification : undefined,
          supportStrategy: intent.kind === 'support_strategy' ? intent.supportStrategy : undefined,
          hintLevel: intent.kind === 'support_strategy' ? intent.hintLevel : undefined,
        })

        if (focusedQuestion && isAcceptableReasoning(text) && shouldTriggerMastery(focusedQuestion.id, focusedQuestion.question, text)) {
          consolidation.updateConceptState(focusedQuestion.id, focusedQuestion.question, current => ({
            ...current,
            questionText: focusedQuestion.question,
            explanationHistory: [...current.explanationHistory, text],
          }))
          await consolidation.startMasteryCheck(focusedQuestion.id, focusedQuestion.question, text)
        } else if (focusedQuestion && isAcceptableReasoning(text)) {
          consolidation.updateConceptState(focusedQuestion.id, focusedQuestion.question, current => ({
            ...current,
            questionText: focusedQuestion.question,
            explanationHistory: [...current.explanationHistory, text],
          }))
        }
      }
    } finally {
      sendInFlightRef.current = false
      console.debug('[controller] handleSend complete, sendInFlight cleared')
    }
  }

  return {
    scaffoldScore,
    currentLevel,
    pendingExplanation,
    messages,
    isTutorLoading,
    addTextMessage,
    getMessageTimestamp,
    handleAnswer,
    handleHint,
    handleReword,
    handleSend,
    consolidation: consolidation.consolidation,
    awaitingChoice: consolidation.awaitingChoice,
    remediation: consolidation.remediation,
    handleConsolidationAnswer: consolidation.handleConsolidationAnswer,
    handleChoice: consolidation.handleChoice,
    handleRemediationAnswer: consolidation.handleRemediationAnswer,
    handleInterventionChoice: consolidation.handleInterventionChoice,
    handlePostInterventionAnswer: consolidation.handlePostInterventionAnswer,
  }
}
