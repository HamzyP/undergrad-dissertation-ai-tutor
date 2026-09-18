import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import Quiz from './Quiz'

const sampleQuestions = [
  {
    id: 1,
    question: 'What is 2+2?',
    options: ['3', '4', '5', '6'],
    correctIndex: 1
  },
  {
    id: 2,
    question: 'What is 3+3?',
    options: ['5', '6', '7', '8'],
    correctIndex: 1
  }
]

describe('Quiz', () => {
  it('renders the title and first question', () => {
    render(<Quiz title="Test Quiz" questions={sampleQuestions} onComplete={() => {}} />)
    expect(screen.getByText('Test Quiz')).toBeInTheDocument()
    expect(screen.getByText('What is 2+2?')).toBeInTheDocument()
  })

  it('disables submit button when no option is selected', () => {
    render(<Quiz title="Test Quiz" questions={sampleQuestions} onComplete={() => {}} />)
    expect(screen.getByRole('button', { name: /submit answer/i })).toBeDisabled()
  })

  it('calls onComplete with correct score when all answers are right', async () => {
    const user = userEvent.setup()
    const onComplete = vi.fn()
    render(<Quiz title="Test Quiz" questions={sampleQuestions} onComplete={onComplete} />)

    // Question 1 — correct answer is index 1
    await user.click(screen.getByLabelText('4'))
    await user.click(screen.getByRole('button', { name: /submit answer/i }))

    // Question 2 — correct answer is index 1
    await user.click(screen.getByLabelText('6'))
    await user.click(screen.getByRole('button', { name: /submit answer/i }))

    expect(onComplete).toHaveBeenCalledWith(2, 2)
  })

  it('calls onComplete with partial score when some answers are wrong', async () => {
    const user = userEvent.setup()
    const onComplete = vi.fn()
    render(<Quiz title="Test Quiz" questions={sampleQuestions} onComplete={onComplete} />)

    // Question 1 — wrong answer
    await user.click(screen.getByLabelText('3'))
    await user.click(screen.getByRole('button', { name: /submit answer/i }))

    // Question 2 — correct answer
    await user.click(screen.getByLabelText('6'))
    await user.click(screen.getByRole('button', { name: /submit answer/i }))

    expect(onComplete).toHaveBeenCalledWith(1, 2)
  })
})