import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

type Group = 'A' | 'B' | 'C' | 'D'

interface ConsentState {
  info: boolean
  age: boolean
  stem: boolean
  consentForm: boolean
  postSessionQuestionnaire: boolean
}

interface WelcomeViewProps {
  participantId: string
  onStart: (group: Group, model: string, consent: ConsentState) => void
}

interface ModelListResponse {
  models: string[]
  default_model: string
  error?: string
}

const groupDescriptions: Record<Group, string> = {
  A: 'Liberalism (AI) -> Rep. Democracy (video-only)',
  B: 'Liberalism (video-only) -> Rep. Democracy (AI)',
  C: 'Rep. Democracy (AI) -> Liberalism (video-only)',
  D: 'Rep. Democracy (video-only) -> Liberalism (AI)',
}

function WelcomeView({ participantId, onStart }: WelcomeViewProps) {
  const navigate = useNavigate()
  const [selectedGroup, setSelectedGroup] = useState<Group>('A')
  const [models, setModels] = useState<string[]>([])
  const [selectedModel, setSelectedModel] = useState('')
  const [isLoadingModels, setIsLoadingModels] = useState(true)
  const [loadError, setLoadError] = useState('')

  useEffect(() => {
    let isActive = true

    const loadModels = async () => {
      setIsLoadingModels(true)
      setLoadError('')

      try {
        const response = await fetch('http://127.0.0.1:8000/api/models')
        const data: ModelListResponse = await response.json()

        if (!response.ok) {
          throw new Error(data.error || `Model request failed with status ${response.status}`)
        }

        if (!isActive) return

        setModels(data.models)
        setSelectedModel(data.default_model || data.models[0] || '')
      } catch (error) {
        console.error('Failed to load local models:', error)
        if (!isActive) return
        setModels([])
        setSelectedModel('')
        setLoadError('Could not load downloaded local models. Check the backend and Ollama setup.')
      } finally {
        if (isActive) {
          setIsLoadingModels(false)
        }
      }
    }

    loadModels()

    return () => {
      isActive = false
    }
  }, [])

  const handleSubmit = () => {
    if (!selectedModel) return
    onStart(selectedGroup, selectedModel, consentChecks)
  }

  const [consentChecks, setConsentChecks] = useState({
    info: false,
    age: false,
    stem: false,
    consentForm: false,
    postSessionQuestionnaire: false,
  })
  const allChecked = Object.values(consentChecks).every(Boolean)

  const startDisabled = isLoadingModels || !selectedModel || !allChecked

  return (
    <main className="welcome-view">
      <button className="admin-nav-btn" onClick={() => navigate('/admin')} aria-label="Go to admin panel">
        Admin →
      </button>

      <h1>RAG-Grounded LLM Tutoring System</h1>

      <div className="participant-id-banner" aria-label="Participant ID">
        <span className="participant-id-label">Participant ID</span>
        <span className="participant-id-value">{participantId}</span>
      </div>

      <section className="consent-panel" aria-label="Eligibility and consent">
        <h2>Eligibility &amp; consent</h2>
        <p className="consent-intro">Please read and confirm each of the following before proceeding.</p>
        <ul className="consent-checklist">
          <li>
            <label className="consent-item">
              <input type="checkbox" checked={consentChecks.info} onChange={e => setConsentChecks(c => ({ ...c, info: e.target.checked }))} />
              <span>I have read and understood the <a href="/docs/Participant_Information_Sheet.pdf" target="_blank" rel="noopener noreferrer">participant information sheet</a>.</span>
            </label>
          </li>
          <li>
            <label className="consent-item">
              <input type="checkbox" checked={consentChecks.age} onChange={e => setConsentChecks(c => ({ ...c, age: e.target.checked }))} />
              <span>I am over the age of 18.</span>
            </label>
          </li>
          <li>
            <label className="consent-item">
              <input type="checkbox" checked={consentChecks.stem} onChange={e => setConsentChecks(c => ({ ...c, stem: e.target.checked }))} />
              <span>I am a university student studying a STEM subject (e.g. Computer Science, Engineering, Mathematics, or Physics).</span>
            </label>
          </li>
          <li>
            <label className="consent-item">
              <input type="checkbox" checked={consentChecks.consentForm} onChange={e => setConsentChecks(c => ({ ...c, consentForm: e.target.checked }))} />
              <span>I have read and understood the <a href="/docs/Participant_Consent_Form.pdf" target="_blank" rel="noopener noreferrer">consent form</a> and agree to participate in this experiment.</span>
            </label>
          </li>
          <li>
            <label className="consent-item">
              <input
                type="checkbox"
                checked={consentChecks.postSessionQuestionnaire}
                onChange={e => setConsentChecks(c => ({ ...c, postSessionQuestionnaire: e.target.checked }))}
              />
              <span>I understand that there is an optional post-session questionnaire I will be invited to complete after the study, and that my responses will be anonymous and linked only by my participant ID.</span>
            </label>
          </li>
        </ul>
      </section>

      <section className="settings-panel" aria-label="Participant and model settings">
        <h2>Session settings</h2>

        <div className="settings-field">
          <span className="settings-label">Participant type</span>
          <div className="group-options" role="radiogroup" aria-label="Participant type">
            {(['A', 'B', 'C', 'D'] as Group[]).map(group => (
              <label
                key={group}
                className={`group-option ${selectedGroup === group ? 'selected' : ''}`}
              >
                <input
                  type="radio"
                  name="participant-group"
                  value={group}
                  checked={selectedGroup === group}
                  onChange={() => setSelectedGroup(group)}
                />
                <div className="group-option-content">
                  <span className="group-option-title">Group {group}</span>
                  <span className="group-option-description">{groupDescriptions[group]}</span>
                </div>
              </label>
            ))}
          </div>
        </div>

        <div className="settings-field">
          <label className="settings-label" htmlFor="model-select">
            Downloaded local model
          </label>
          <select
            id="model-select"
            value={selectedModel}
            onChange={(event) => setSelectedModel(event.target.value)}
            disabled={isLoadingModels || models.length === 0}
          >
            {isLoadingModels && <option value="">Loading models...</option>}
            {!isLoadingModels && models.length === 0 && <option value="">No local models found</option>}
            {!isLoadingModels &&
              models.map(model => (
                <option key={model} value={model}>
                  {model}
                </option>
              ))}
          </select>
          {loadError && <p className="settings-error">{loadError}</p>}
          {!loadError && !isLoadingModels && selectedModel && (
            <p className="settings-help">Selected model: {selectedModel}</p>
          )}
        </div>

        <button className="start-button" onClick={handleSubmit} disabled={startDisabled}>
          Start session
        </button>
      </section>
    </main>
  )
}

export default WelcomeView
