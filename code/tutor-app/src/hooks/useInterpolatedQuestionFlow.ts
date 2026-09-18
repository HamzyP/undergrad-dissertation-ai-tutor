import { useState } from 'react'
import type { InterpolatedQuestion } from '../QuestionOverlay'

interface UseInterpolatedQuestionFlowOptions {
  questions: InterpolatedQuestion[]
  pauseVideo: () => void
  onAnswer: (correct: boolean, attempts: number, selectedOption: number, question: InterpolatedQuestion) => void
  /** Return true to suppress question triggers (e.g. consolidation or explanation pending) */
  isBusy: () => boolean
}

export function useInterpolatedQuestionFlow({
  questions,
  pauseVideo,
  onAnswer,
  isBusy,
}: UseInterpolatedQuestionFlowOptions) {
  const [activeQuestion, setActiveQuestion] = useState<InterpolatedQuestion | null>(null)
  const [answeredIds, setAnsweredIds] = useState<number[]>([])

  const markers = questions.map(q => q.timestamp)

  const handleTimeUpdate = (time: number) => {
    if (isBusy() || activeQuestion) return
    for (const q of questions) {
      // timeupdate events fire irregularly (e.g., every ~250ms). 
      // This 1-second window ensures we don't miss the exact timestamp.
      if (!answeredIds.includes(q.id) && time >= q.timestamp && time < q.timestamp + 1) {
        setActiveQuestion(q)
        pauseVideo()
        break
      }
    }
  }

  const handleAnswer = (correct: boolean, attempts: number, selectedOption: number) => {
    if (!activeQuestion) return
    const question = activeQuestion
    setActiveQuestion(null)
    setAnsweredIds(prev => [...prev, question.id])
    onAnswer(correct, attempts, selectedOption, question)
  }

  const dismissActiveQuestion = () => setActiveQuestion(null)
  const updateActiveQuestion = (updated: InterpolatedQuestion) => setActiveQuestion(updated)

  return {
    activeQuestion,
    markers,
    handleTimeUpdate,
    handleAnswer,
    dismissActiveQuestion,
    updateActiveQuestion,
  }
}
