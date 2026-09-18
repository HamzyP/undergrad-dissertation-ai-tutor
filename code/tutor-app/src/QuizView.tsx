import { useEffect, useState } from 'react'
import Quiz from './Quiz'

interface ApiQuestion {
  id: number
  question_text: string
  options: string[]
  correct_index: number
}

type Topic = 'liberalism' | 'rep-democracy'

const TOPIC_LABELS: Record<Topic, string> = {
  liberalism: 'Liberalism',
  'rep-democracy': 'Representative Democracy',
}

interface TopicScore {
  topic: Topic
  correct: number
  total: number
}

interface QuizViewProps {
  // Order the two topics are presented — matches the participant's video sequence
  topicOrder: [Topic, Topic]
  quizType: 'pre' | 'post'
  onComplete: (scores: [TopicScore, TopicScore]) => void
}

function shuffled<T>(arr: T[]): T[] {
  const copy = [...arr]
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[copy[i], copy[j]] = [copy[j], copy[i]]
  }
  return copy
}

function toQuizQuestions(qs: ApiQuestion[], shuffle: boolean) {
  const mapped = qs.map(q => ({
    id: q.id,
    question: q.question_text,
    options: q.options,
    correctIndex: q.correct_index,
  }))
  return shuffle ? shuffled(mapped) : mapped
}

export default function QuizView({ topicOrder, quizType, onComplete }: QuizViewProps) {
  const [questions, setQuestions] = useState<Record<Topic, ApiQuestion[]>>({ liberalism: [], 'rep-democracy': [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [sectionIndex, setSectionIndex] = useState(0)          // 0 = first topic, 1 = second topic
  const [scores, setScores] = useState<TopicScore[]>([])
  const [betweenSections, setBetweenSections] = useState(false)

  const isPost = quizType === 'post'
  const title = isPost ? 'Post-Quiz' : 'Pre-Quiz'

  useEffect(() => {
    const fetches = topicOrder.map(topic =>
      fetch(`http://127.0.0.1:8000/api/questions/?topic=${topic}&quiz_type=pre`)
        .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
        .then((qs: ApiQuestion[]) => ({ topic, qs }))
    )
    Promise.all(fetches)
      .then(results => {
        const map = { liberalism: [], 'rep-democracy': [] } as Record<Topic, ApiQuestion[]>
        results.forEach(({ topic, qs }) => { map[topic] = qs })
        setQuestions(map)
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <main className="quiz-view"><p>Loading questions…</p></main>
  if (error)   return <main className="quiz-view"><p>Failed to load questions: {error}</p></main>

  const currentTopic = topicOrder[sectionIndex]
  const currentLabel = TOPIC_LABELS[currentTopic]
  const currentQuestions = toQuizQuestions(questions[currentTopic], isPost)

  if (currentQuestions.length === 0) {
    return <main className="quiz-view"><p>No {title} questions available for {currentLabel} yet.</p></main>
  }

  const handleSectionComplete = (correct: number, total: number) => {
    const newScore: TopicScore = { topic: currentTopic, correct, total }
    const newScores = [...scores, newScore]
    setScores(newScores)

    if (sectionIndex < topicOrder.length - 1) {
      setBetweenSections(true)
    } else {
      onComplete(newScores as [TopicScore, TopicScore])
    }
  }

  const handleContinueToNext = () => {
    setBetweenSections(false)
    setSectionIndex(i => i + 1)
  }

  if (betweenSections) {
    const nextLabel = TOPIC_LABELS[topicOrder[sectionIndex + 1]]
    return (
      <main className="quiz-view">
        <div className="quiz-section-transition">
          <p className="quiz-section-transition-done">✓ {currentLabel} section complete.</p>
          <h2>Section 1 of 2 done.</h2>
          <p>When you are ready, continue to the <strong>{nextLabel}</strong> questions.</p>
          <button className="quiz-next-btn" onClick={handleContinueToNext}>
            Continue to {nextLabel} questions
          </button>
        </div>
      </main>
    )
  }

  return (
    <main className="quiz-view">
      <div className="quiz-section-header">
        <span className="quiz-section-pill">
          Part {sectionIndex + 1} of {topicOrder.length} — {currentLabel}
        </span>
      </div>
      <Quiz
        title={title}
        questions={currentQuestions}
        onComplete={handleSectionComplete}
      />
    </main>
  )
}
