import { useState } from 'react'

interface Question {
  id: number
  question: string
  options: string[]
  correctIndex: number
}

interface QuizProps {
  title: string
  questions: Question[]
  onComplete: (score: number, total: number) => void
}

function Quiz({ title, questions, onComplete }: QuizProps) {
  const [currentIndex, setCurrentIndex] = useState(0)
  const [selectedOption, setSelectedOption] = useState<number | null>(null)
  const [score, setScore] = useState(0)
  const [finished, setFinished] = useState(false)

  const current = questions[currentIndex]

  const handleSubmit = () => {
    if (selectedOption === null) return

    const newScore = selectedOption === current.correctIndex ? score + 1 : score

    if (currentIndex < questions.length - 1) {
      setScore(newScore)
      setCurrentIndex(currentIndex + 1)
      setSelectedOption(null)
    } else {
      setScore(newScore)
      setFinished(true)
      onComplete(newScore, questions.length)
    }
  }

  if (finished) {
    return (
      <section className="quiz" aria-label="Quiz results">
        <h2>{title} — Complete</h2>
        <p className="quiz-score">You scored {score} out of {questions.length}</p>
      </section>
    )
  }

  return (
    <section className="quiz" aria-label={title}>
      <h2>{title}</h2>
      <p className="quiz-progress">Question {currentIndex + 1} of {questions.length}</p>
      <p className="quiz-question">{current.question}</p>
      <div className="quiz-options" role="radiogroup" aria-label="Answer options">
        {current.options.map((option, index) => (
          <label
            key={index}
            className={`quiz-option ${selectedOption === index ? 'selected' : ''}`}
          >
            <input
              type="radio"
              name="quiz-answer"
              checked={selectedOption === index}
              onChange={() => setSelectedOption(index)}
              aria-label={option}
            />
            <span>{option}</span>
          </label>
        ))}
      </div>
      <button
        className="quiz-submit"
        onClick={handleSubmit}
        disabled={selectedOption === null}
        aria-label="Submit answer"
      >
        {currentIndex < questions.length - 1 ? 'Next' : 'Finish'}
      </button>
    </section>
  )
}

export default Quiz