import { useState } from 'react'

const MAX_ATTEMPTS = 2
const CORRECT_FEEDBACK = 'Correct! Now explain in the chat why.'
const RETRY_FEEDBACK = 'Not quite - try again.'

interface InterpolatedQuestion {
  id: number
  question: string
  options: string[]
  correctIndex: number
  timestamp: number
  rewatchStart: number
}

interface QuestionOverlayProps {
  question: InterpolatedQuestion
  onAnswer: (correct: boolean, attempts: number, selectedOption: number) => void
  onHint: () => void
  onRewatch: () => void
  onReword: () => void
}

function getSubmissionOutcome(
  selectedOption: number,
  correctIndex: number,
  attempts: number,
): 'correct' | 'retry' | 'incorrect' {
  if (selectedOption === correctIndex) return 'correct'
  if (attempts >= MAX_ATTEMPTS) return 'incorrect'
  return 'retry'
}

function QuestionOverlay({ question, onAnswer, onHint, onRewatch, onReword }: QuestionOverlayProps) {
  const [selectedOption, setSelectedOption] = useState<number | null>(null)
  const [attempts, setAttempts] = useState(0)
  const [feedback, setFeedback] = useState<string | null>(null)
  const [hasReworded, setHasReworded] = useState(false)
  const [hasHinted, setHasHinted] = useState(false)

  const isResolved = feedback === CORRECT_FEEDBACK || attempts >= MAX_ATTEMPTS

  function handleSubmit() {
    if (selectedOption === null) return

    const nextAttempts = attempts + 1
    const outcome = getSubmissionOutcome(selectedOption, question.correctIndex, nextAttempts)

    switch (outcome) {
      case 'correct':
        setFeedback(CORRECT_FEEDBACK)
        setAttempts(nextAttempts)
        // Small delay before notifying parent so the learner sees feedback.
        setTimeout(() => onAnswer(true, nextAttempts, selectedOption), 1500)
        break

      case 'incorrect':
        setFeedback(`The correct answer was: ${question.options[question.correctIndex]}`)
        setAttempts(nextAttempts)
        setTimeout(() => onAnswer(false, nextAttempts, selectedOption), 2000)
        break

      case 'retry':
        setFeedback(RETRY_FEEDBACK)
        setAttempts(nextAttempts)
        setSelectedOption(null)
        break
    }
  }

  function handleReword() {
    if (hasReworded) return
    setHasReworded(true)
    onReword()
  }

  return (
    <div className="question-overlay" role="dialog" aria-label="Interpolated question">
      <div className="question-card">
        <p className="question-text">{question.question}</p>

        <div className="question-options" role="radiogroup" aria-label="Answer options">
          {question.options.map((option, index) => (
            <label
              key={index}
              className={`question-option ${selectedOption === index ? 'selected' : ''}`}
            >
              <input
                type="radio"
                name="question-answer"
                checked={selectedOption === index}
                onChange={() => setSelectedOption(index)}
                disabled={isResolved}
              />
              <span>{option}</span>
            </label>
          ))}
        </div>

        {feedback && <p className="question-feedback">{feedback}</p>}

        <div className="question-actions">
          <button
            className="question-submit"
            onClick={handleSubmit}
            disabled={selectedOption === null || isResolved}
          >
            Submit
          </button>
          <button
            onClick={() => { setHasHinted(true); onHint() }}
            disabled={hasHinted}
            aria-label="Request a hint"
          >
            {hasHinted ? 'Hint used' : 'Hint'}
          </button>
          <button onClick={onRewatch} aria-label="Rewatch relevant section">
            Rewatch
          </button>
          <button
            onClick={handleReword}
            disabled={hasReworded}
            aria-label="Reword the question"
          >
            {hasReworded ? 'Reworded' : 'Reword'}
          </button>
        </div>
      </div>
    </div>
  )
}

export type { InterpolatedQuestion }
export default QuestionOverlay
