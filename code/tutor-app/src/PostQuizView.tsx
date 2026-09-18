import QuizView from './QuizView'

type Topic = 'liberalism' | 'rep-democracy'

interface TopicScore {
  topic: Topic
  correct: number
  total: number
}

interface PostQuizViewProps {
  topicOrder: [Topic, Topic]
  onComplete: (scores: [TopicScore, TopicScore]) => void
}

export default function PostQuizView({ topicOrder, onComplete }: PostQuizViewProps) {
  return <QuizView topicOrder={topicOrder} quizType="post" onComplete={onComplete} />
}
