import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import QuestionOverlay from './QuestionOverlay'

const sampleQuestion = {
  id: 1,
  question: 'What is the core principle?',
  options: ['Freedom', 'Authority', 'Tradition', 'Power'],
  correctIndex: 0,
  timestamp: 15,
  rewatchStart: 5
}

describe('QuestionOverlay', () => {
  it('renders the question and all four options', () => {
    render(
      <QuestionOverlay
        question={sampleQuestion}
        onAnswer={() => {}}
        onHint={() => {}}
        onRewatch={() => {}}
        onReword={() => {}}
      />
    )
    expect(screen.getByText('What is the core principle?')).toBeInTheDocument()
    expect(screen.getByLabelText('Freedom')).toBeInTheDocument()
    expect(screen.getByLabelText('Authority')).toBeInTheDocument()
    expect(screen.getByLabelText('Tradition')).toBeInTheDocument()
    expect(screen.getByLabelText('Power')).toBeInTheDocument()
  })

  it('disables submit button when no option is selected', () => {
    render(
      <QuestionOverlay
        question={sampleQuestion}
        onAnswer={() => {}}
        onHint={() => {}}
        onRewatch={() => {}}
        onReword={() => {}}
      />
    )
    expect(screen.getByRole('button', { name: 'Submit' })).toBeDisabled()
  })

  it('calls onAnswer with correct=true and attempts=1 when first answer is right', async () => {
    const user = userEvent.setup()
    const onAnswer = vi.fn()
    render(
      <QuestionOverlay
        question={sampleQuestion}
        onAnswer={onAnswer}
        onHint={() => {}}
        onRewatch={() => {}}
        onReword={() => {}}
      />
    )

    await user.click(screen.getByLabelText('Freedom'))
    await user.click(screen.getByRole('button', { name: 'Submit' }))

    await waitFor(() => {
      expect(onAnswer).toHaveBeenCalledWith(true, 1, 0)
    }, { timeout: 2000 })
  })

  it('shows feedback and lets user retry after wrong answer', async () => {
    const user = userEvent.setup()
    const onAnswer = vi.fn()
    render(
      <QuestionOverlay
        question={sampleQuestion}
        onAnswer={onAnswer}
        onHint={() => {}}
        onRewatch={() => {}}
        onReword={() => {}}
      />
    )

    await user.click(screen.getByLabelText('Authority'))
    await user.click(screen.getByRole('button', { name: 'Submit' }))

    expect(screen.getByText(/not quite/i)).toBeInTheDocument()
    expect(onAnswer).not.toHaveBeenCalled()
  })

  it('reveals correct answer and calls onAnswer after 2 wrong attempts', async () => {
    const user = userEvent.setup()
    const onAnswer = vi.fn()
    render(
      <QuestionOverlay
        question={sampleQuestion}
        onAnswer={onAnswer}
        onHint={() => {}}
        onRewatch={() => {}}
        onReword={() => {}}
      />
    )

    // Two wrong attempts in a row
    for (let i = 0; i < 2; i++) {
      await user.click(screen.getByLabelText('Authority'))
      await user.click(screen.getByRole('button', { name: 'Submit' }))
    }

    expect(screen.getByText(/correct answer was: Freedom/i)).toBeInTheDocument()

    await waitFor(() => {
      expect(onAnswer).toHaveBeenCalledWith(false, 2, 1)
    }, { timeout: 3000 })
  })

  it('calls onHint when hint button is clicked', async () => {
    const user = userEvent.setup()
    const onHint = vi.fn()
    render(
      <QuestionOverlay
        question={sampleQuestion}
        onAnswer={() => {}}
        onHint={onHint}
        onRewatch={() => {}}
        onReword={() => {}}
      />
    )

    await user.click(screen.getByRole('button', { name: /request a hint/i }))
    expect(onHint).toHaveBeenCalledTimes(1)
  })

  it('calls onRewatch when rewatch button is clicked', async () => {
    const user = userEvent.setup()
    const onRewatch = vi.fn()
    render(
      <QuestionOverlay
        question={sampleQuestion}
        onAnswer={() => {}}
        onHint={() => {}}
        onRewatch={onRewatch}
        onReword={() => {}}
      />
    )

    await user.click(screen.getByRole('button', { name: /rewatch relevant section/i }))
    expect(onRewatch).toHaveBeenCalledTimes(1)
  })

  it('only allows reword to be called once per question', async () => {
    const user = userEvent.setup()
    const onReword = vi.fn()
    render(
      <QuestionOverlay
        question={sampleQuestion}
        onAnswer={() => {}}
        onHint={() => {}}
        onRewatch={() => {}}
        onReword={onReword}
      />
    )

    const rewordButton = screen.getByRole('button', { name: /reword the question/i })
    await user.click(rewordButton)
    await user.click(rewordButton)

    expect(onReword).toHaveBeenCalledTimes(1)
    expect(rewordButton).toBeDisabled()
  })
})
