import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import RagDebugTab from './admin/RagDebugTab'
import QuestionsTab from './admin/QuestionsTab'
import ParticipantsTab from './admin/ParticipantsTab'

type AdminTab = 'rag-debug' | 'questions' | 'participants'
type Theme = 'light' | 'dark' | 'high-contrast' | 'cb-deuteranopia' | 'cb-protanopia' | 'cb-tritanopia' | 'cb-achromatopsia'

const CB_THEMES: { value: Theme; label: string; desc: string }[] = [
  { value: 'cb-deuteranopia',   label: 'Deuteranopia',   desc: 'Red-green (most common)' },
  { value: 'cb-protanopia',     label: 'Protanopia',     desc: 'Red-green (reds darkened)' },
  { value: 'cb-tritanopia',     label: 'Tritanopia',     desc: 'Blue-yellow confusion' },
  { value: 'cb-achromatopsia',  label: 'Achromatopsia',  desc: 'Full colour blindness' },
]

export default function AdminView() {
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState<AdminTab>(() => {
    const saved = localStorage.getItem('admin-active-tab')
    return (saved === 'rag-debug' || saved === 'questions' || saved === 'participants') ? saved : 'questions'
  })
  const [availableModels, setAvailableModels] = useState<string[]>([])
  const [theme, setTheme] = useState<Theme>('dark')
  const [cbOpen, setCbOpen] = useState(false)
  const cbRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetch('http://127.0.0.1:8000/api/models')
      .then(r => r.json())
      .then(data => setAvailableModels(data.models ?? []))
      .catch(() => {})
  }, [])

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (cbRef.current && !cbRef.current.contains(e.target as Node)) {
        setCbOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  const isCb = theme.startsWith('cb-')

  return (
    <div className={`admin-view ${theme}`}>
      <header className="admin-header">
        <button className="admin-back-btn" onClick={() => navigate('/')} aria-label="Back to learner">
          ← Back
        </button>

        <h1>Tutor Admin</h1>

        <nav className="admin-tabs">
          <button
            className={`admin-tab admin-tab--nav ${activeTab === 'questions' ? 'admin-tab--active' : ''}`}
            onClick={() => { setActiveTab('questions'); localStorage.setItem('admin-active-tab', 'questions') }}
          >
            Questions
          </button>
          <button
            className={`admin-tab admin-tab--nav ${activeTab === 'participants' ? 'admin-tab--active' : ''}`}
            onClick={() => { setActiveTab('participants'); localStorage.setItem('admin-active-tab', 'participants') }}
          >
            Participants
          </button>
          <button
            className={`admin-tab admin-tab--nav ${activeTab === 'rag-debug' ? 'admin-tab--active' : ''}`}
            onClick={() => { setActiveTab('rag-debug'); localStorage.setItem('admin-active-tab', 'rag-debug') }}
          >
            RAG Debug
          </button>
        </nav>

        <nav className="theme-switcher admin-theme-switcher" aria-label="Display mode">
          <button className={theme === 'light' ? 'active' : ''} onClick={() => { setTheme('light'); setCbOpen(false) }}>Light</button>
          <button className={theme === 'dark' ? 'active' : ''} onClick={() => { setTheme('dark'); setCbOpen(false) }}>Dark</button>
          <button className={theme === 'high-contrast' ? 'active' : ''} onClick={() => { setTheme('high-contrast'); setCbOpen(false) }}>High Contrast</button>

          <div className="cb-dropdown" ref={cbRef}>
            <button
              className={isCb ? 'active' : ''}
              onClick={() => setCbOpen(o => !o)}
              aria-haspopup="listbox"
              aria-expanded={cbOpen}
            >
              {isCb ? CB_THEMES.find(t => t.value === theme)!.label : 'Colourblind'} ▾
            </button>
            {cbOpen && (
              <ul className="cb-dropdown__menu" role="listbox">
                {CB_THEMES.map(t => (
                  <li
                    key={t.value}
                    role="option"
                    aria-selected={theme === t.value}
                    className={theme === t.value ? 'cb-dropdown__item cb-dropdown__item--active' : 'cb-dropdown__item'}
                    onClick={() => { setTheme(t.value); setCbOpen(false) }}
                  >
                    <span className="cb-dropdown__label">{t.label}</span>
                    <span className="cb-dropdown__desc">{t.desc}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </nav>
      </header>

      <main className="admin-main">
        {activeTab === 'rag-debug' && <RagDebugTab />}
        {activeTab === 'questions' && <QuestionsTab availableModels={availableModels} />}
        {activeTab === 'participants' && <ParticipantsTab />}
      </main>
    </div>
  )
}
