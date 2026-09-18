import { useState, useEffect } from 'react'
import type { InterpolatedQuestion } from '../QuestionOverlay'
import { logTutorConsoleError } from '../lib/tutorUtils'

interface ApiQuestion {
  id: number
  question_text: string
  options: string[]
  correct_index: number
  timestamp: number
  rewatch_start: number
}

export function useInterpolatedQuestions(topic: string) {
  const [questions, setQuestions] = useState<InterpolatedQuestion[]>([])
  const [questionsLoaded, setQuestionsLoaded] = useState(false)

  useEffect(() => {
    fetch(`http://127.0.0.1:8000/api/questions/?topic=${topic}&quiz_type=interpolated`)
      .then(r => r.json())
      .then((data: ApiQuestion[]) => {
        setQuestions(data.map(q => ({
          id: q.id,
          question: q.question_text,
          options: q.options,
          correctIndex: q.correct_index,
          timestamp: q.timestamp ?? 0,
          rewatchStart: q.rewatch_start ?? 0,
        })))
      })
      .catch(error => {
        logTutorConsoleError('QUESTION_LOAD', 'Failed to load interpolated questions.', { topic, error })
      })
      .finally(() => setQuestionsLoaded(true))
  }, [topic])

  return { questions, questionsLoaded }
}
