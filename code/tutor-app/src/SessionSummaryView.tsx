type Topic = 'liberalism' | 'rep-democracy'

interface TopicScore { topic: Topic; correct: number; total: number }

const TOPIC_LABELS: Record<Topic, string> = {
  liberalism: 'Liberalism',
  'rep-democracy': 'Representative Democracy',
}

interface SessionSummaryViewProps {
  topicOrder: [Topic, Topic]
  preScores: TopicScore[]
  postScores: TopicScore[]
  onContinue: () => void
}

function pct(correct: number, total: number) {
  return total > 0 ? Math.round((correct / total) * 100) : 0
}

export default function SessionSummaryView({ topicOrder, preScores, postScores, onContinue }: SessionSummaryViewProps) {
  const rows = topicOrder.map(topic => {
    const pre  = preScores.find(s => s.topic === topic)
    const post = postScores.find(s => s.topic === topic)
    const prePct  = pre  ? pct(pre.correct,  pre.total)  : null
    const postPct = post ? pct(post.correct, post.total) : null
    const gain = prePct !== null && postPct !== null ? postPct - prePct : null
    return { topic, label: TOPIC_LABELS[topic], pre, post, prePct, postPct, gain }
  })

  const totalPreCorrect  = preScores.reduce((s, r) => s + r.correct, 0)
  const totalPreTotal    = preScores.reduce((s, r) => s + r.total,   0)
  const totalPostCorrect = postScores.reduce((s, r) => s + r.correct, 0)
  const totalPostTotal   = postScores.reduce((s, r) => s + r.total,   0)
  const totalPrePct      = pct(totalPreCorrect, totalPreTotal)
  const totalPostPct     = pct(totalPostCorrect, totalPostTotal)
  const totalGain        = totalPostPct - totalPrePct

  return (
    <main className="quiz-view">
      <h2>Session Summary</h2>
      <table className="summary-table" aria-label="Quiz score comparison">
        <thead>
          <tr>
            <th>Topic</th>
            <th>Pre-quiz</th>
            <th>Post-quiz</th>
            <th>Change</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.topic}>
              <td>{r.label}</td>
              <td>{r.pre ? `${r.pre.correct}/${r.pre.total} (${r.prePct}%)` : '—'}</td>
              <td>{r.post ? `${r.post.correct}/${r.post.total} (${r.postPct}%)` : '—'}</td>
              <td className={r.gain !== null && r.gain > 0 ? 'gain-positive' : r.gain !== null && r.gain < 0 ? 'gain-negative' : ''}>
                {r.gain !== null ? (r.gain > 0 ? `+${r.gain}%` : `${r.gain}%`) : '—'}
              </td>
            </tr>
          ))}
          <tr className="summary-gain">
            <td><strong>Overall</strong></td>
            <td>{totalPreCorrect}/{totalPreTotal} ({totalPrePct}%)</td>
            <td>{totalPostCorrect}/{totalPostTotal} ({totalPostPct}%)</td>
            <td className={totalGain > 0 ? 'gain-positive' : totalGain < 0 ? 'gain-negative' : ''}>
              {totalGain > 0 ? `+${totalGain}%` : `${totalGain}%`}
            </td>
          </tr>
        </tbody>
      </table>
      <button className="quiz-next-btn" onClick={onContinue}>Finish</button>
    </main>
  )
}
