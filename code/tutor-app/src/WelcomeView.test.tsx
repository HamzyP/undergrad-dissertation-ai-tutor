import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import WelcomeView from './WelcomeView'

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return { ...actual, useNavigate: () => vi.fn() }
})

// Suppress the models fetch — not under test here
beforeEach(() => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify({ models: ['llama3'], default_model: 'llama3' }), { status: 200 })
  )
})

afterEach(() => vi.restoreAllMocks())

function renderWelcome(participantId = '12345') {
  return render(
    <MemoryRouter>
      <WelcomeView participantId={participantId} onStart={vi.fn()} />
    </MemoryRouter>
  )
}

describe('WelcomeView', () => {
  it('displays the participant ID prominently', () => {
    renderWelcome('42789')
    expect(screen.getByText('42789')).toBeInTheDocument()
  })

  it('renders all five consent checkboxes with linked PDFs', () => {
    renderWelcome()
    expect(screen.getByRole('link', { name: /participant information sheet/i }))
      .toHaveAttribute('href', '/docs/Participant_Information_Sheet.pdf')
    expect(screen.getByRole('link', { name: /consent form/i }))
      .toHaveAttribute('href', '/docs/Participant_Consent_Form.pdf')
    expect(screen.getByText(/optional post-session questionnaire/i)).toBeInTheDocument()
    expect(screen.getAllByRole('checkbox')).toHaveLength(5)
  })

  it('renders group selection options A through D', () => {
    renderWelcome()
    for (const group of ['A', 'B', 'C', 'D']) {
      expect(screen.getByText(`Group ${group}`)).toBeInTheDocument()
    }
  })

  it('keeps Start disabled until all five consent checkboxes are ticked', async () => {
    const user = userEvent.setup()
    renderWelcome()
    await screen.findByDisplayValue('llama3')

    const start = screen.getByRole('button', { name: /start session/i })
    expect(start).toBeDisabled()

    const boxes = screen.getAllByRole('checkbox')
    for (const box of boxes.slice(0, 4)) {
      await user.click(box)
    }
    expect(start).toBeDisabled()

    await user.click(boxes[4])
    expect(start).toBeEnabled()
  })

  it('calls onStart with selected group, model, and consent state when Start is clicked', async () => {
    const user = userEvent.setup()
    const onStart = vi.fn()
    render(
      <MemoryRouter>
        <WelcomeView participantId="12345" onStart={onStart} />
      </MemoryRouter>
    )
    await screen.findByDisplayValue('llama3')

    for (const box of screen.getAllByRole('checkbox')) {
      await user.click(box)
    }
    await user.click(screen.getByRole('button', { name: /start session/i }))

    expect(onStart).toHaveBeenCalledWith('A', 'llama3', {
      info: true, age: true, stem: true, consentForm: true, postSessionQuestionnaire: true,
    })
  })
})
