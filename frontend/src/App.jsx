import React, { useEffect, useRef, useState, useLayoutEffect } from 'react'
import './App.css'

export default function App() {
  const backend = (import.meta.env && import.meta.env.VITE_BACKEND_URL) || 'http://localhost:8000'
  const [session, setSession] = useState(null)
  const [messages, setMessages] = useState([])
  const [text, setText] = useState('')
  const [reasoningActive, setReasoningActive] = useState(false)
  const [reasoningDots, setReasoningDots] = useState(0)
  const [toolActivity, setToolActivity] = useState(null)
  const [debugEvents, setDebugEvents] = useState([])
  const [mode, setMode] = useState('research')
  const [draftSections, setDraftSections] = useState({})
  const [chatHeight, setChatHeight] = useState(900)
  const [chatResizing, setChatResizing] = useState(false)
  const [draftWidth, setDraftWidth] = useState(420)
  const [resizing, setResizing] = useState(false)
  const [draftZoom, setDraftZoom] = useState(0.9)
  const [autoScroll, setAutoScroll] = useState(true)
  const [reasoningAutoScroll, setReasoningAutoScroll] = useState(true)
  const wsRef = useRef(null)
  const fileInputRef = useRef(null)
  const messageScrollRef = useRef(null)
  const reasoningScrollRef = useRef(null)

  useEffect(() => {
    if (!reasoningActive) {
      setReasoningDots(0)
      return
    }
    const timer = setInterval(() => setReasoningDots((d) => (d + 1) % 4), 360)
    return () => clearInterval(timer)
  }, [reasoningActive])

  useEffect(() => {
    fetch(backend + '/api/health').catch(() => {})
    fetch(backend + '/api/sessions', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({}),
    })
      .then((r) => r.json())
      .then((s) => setSession(s))
  }, [])

  useEffect(() => {
    if (!session) return
    const wsUrl = backend.replace(/^http/, 'ws') + '/chat/stream?session_id=' + encodeURIComponent(session.id)
    const ws = new WebSocket(wsUrl)

    const overlapSuffixPrefix = (a, b, maxCheck = 200) => {
      const maxK = Math.min(b.length, maxCheck, a.length)
      for (let k = maxK; k > 0; k--) {
        if (a.endsWith(b.slice(0, k))) return k
      }
      return 0
    }

    const applyStreamDelta = (roleKey, delta, fullText) => {
      const resolvedFull = typeof fullText === 'string' ? fullText : null
      setMessages((prev) => {
        const next = [...prev]
        const last = next[next.length - 1]
        if (last && last.role === roleKey && last.streaming) {
          if (resolvedFull !== null) {
            last.text = resolvedFull
          } else if (delta) {
            const existing = last.text || ''
            const k = overlapSuffixPrefix(existing, delta)
            const toAppend = delta.slice(k)
            if (toAppend) last.text = existing + toAppend
          }
          return next
        }
        const initialText = resolvedFull ?? delta
        return [...next, { role: roleKey, text: initialText, streaming: true }]
      })
    }

    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data)
        if (msg.type === 'assistant_delta') {
          applyStreamDelta('assistant', msg.text_delta || '', msg.full_text)
        } else if (msg.type === 'assistant_reasoning_delta') {
          const roleKey = msg.variant === 'summary' ? 'assistant_reasoning_summary' : 'assistant_reasoning'
          setReasoningActive(true)
          applyStreamDelta(roleKey, msg.text_delta || '', msg.full_text)
          appendDebugEvent({
            kind: 'reasoning',
            variant: msg.variant,
            delta: msg.text_delta,
            timestamp: Date.now(),
          })
        } else if (msg.type === 'assistant_reasoning_done') {
          setReasoningActive(false)
        } else if (msg.type === 'draft_update') {
          const key = msg.section || 'draft'
          setDraftSections((prev) => ({
            ...prev,
            [key]: { title: msg.title || key, markdown: msg.markdown || '' },
          }))
          appendToolMessage(`Draft updated: ${msg.title || msg.section || 'draft'}`)
          appendDebugEvent({
            kind: 'draft',
            section: msg.section,
            markdown: msg.markdown,
            timestamp: Date.now(),
          })
        } else if (msg.type === 'tool_event') {
          handleToolEvent(msg)
        } else if (msg.type === 'error') {
          setMessages((prev) => [...prev, { role: 'tool', text: `Error: ${msg.message || msg.code}` }])
        }
      } catch {
        /* ignore malformed frames */
      }
    }

    wsRef.current = ws
    return () => {
      setReasoningActive(false)
      ws.close()
    }
  }, [session])

useLayoutEffect(() => {
  if (autoScroll && messageScrollRef.current) {
    const el = messageScrollRef.current
    el.scrollTop = el.scrollHeight
  }
}, [messages, reasoningActive, autoScroll])

  const reasoningFeed = messages.filter((m) => m.role === 'assistant_reasoning' || m.role === 'assistant_reasoning_summary').slice(-5)

  useLayoutEffect(() => {
    if (reasoningAutoScroll && reasoningScrollRef.current) {
      const el = reasoningScrollRef.current
      el.scrollTop = el.scrollHeight
    }
  }, [reasoningFeed, reasoningActive, reasoningAutoScroll])

  useEffect(() => {
    if (!resizing) return
    const onMove = (e) => {
      const space = document.querySelector('.workspace')
      if (!space) return
      const rect = space.getBoundingClientRect()
      const handleWidth = 12
      const minDraft = 200
      const minConversation = 320
      const maxDraft = Math.max(minDraft, rect.width - minConversation - handleWidth - 12)
      let desired = rect.right - e.clientX
      desired = Math.max(minDraft, Math.min(desired, maxDraft))
      setDraftWidth(desired)
    }
    const onUp = () => setResizing(false)
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [resizing])

  useEffect(() => {
    const computeHeight = () => {
      const shell = document.querySelector('.app-shell')
      if (!shell) return Math.round(window.innerHeight * 1.5)
      const rect = shell.getBoundingClientRect()
      const debug = document.querySelector('.insight-panel')
      const debugRect = debug?.getBoundingClientRect()
      if (!debugRect) return rect.height
      const offsetTop = document.querySelector('.conversation-card')?.getBoundingClientRect().top || 0
      const height = debugRect.bottom - offsetTop
      return Math.max(360, Math.min(1800, height))
    }

    const updateHeight = () => setChatHeight(computeHeight())
    updateHeight()
    window.addEventListener('resize', updateHeight)
    return () => window.removeEventListener('resize', updateHeight)
  }, [])

  useEffect(() => {
    if (!chatResizing) return
    const onMove = (e) => {
      const minHeight = 360
      const maxHeight = 2200
      const delta = e.clientY
      const top = document.querySelector('.conversation-card')?.getBoundingClientRect().top || 0
      const computed = Math.min(Math.max(delta - top, minHeight), maxHeight)
      setChatHeight(computed)
    }
    const onUp = () => setChatResizing(false)
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [chatResizing])
  useEffect(() => {
    const onResize = () => {
      const space = document.querySelector('.workspace')
      if (!space) return
      const rect = space.getBoundingClientRect()
      const handleWidth = 12
      const minConversation = 320
      const minDraft = 200
      let maxDraft = rect.width - minConversation - handleWidth - 12
      if (maxDraft < minDraft) maxDraft = minDraft
      setDraftWidth((current) => Math.min(Math.max(minDraft, current), maxDraft))
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [draftWidth])

  const send = () => {
    const t = text.trim()
    if (!t || !wsRef.current) return
    setMessages((prev) => [...prev, { role: 'user', text: t, meta: { mode } }])
    wsRef.current.send(JSON.stringify({ type: 'user_message', text: t, mode }))
    setText('')
  }

  const onUpload = async (e) => {
    const files = Array.from(e.target.files || [])
    if (files.length === 0) return
    const fd = new FormData()
    for (const f of files) fd.append('files', f)
    const sid = session?.id ? encodeURIComponent(session.id) : 'default'
    const res = await fetch(`${backend}/api/uploads?session_id=${sid}`, { method: 'POST', body: fd })
    const json = await res.json()
    setMessages((prev) => [
      ...prev,
      { role: 'tool', text: 'Upload processed: ' + (json?.documents?.map((d) => `${d.name} (${d.mode})`).join(', ') || '') },
    ])
  }

  const triggerUpload = () => fileInputRef.current?.click()

  const roleLabel = {
    assistant_reasoning: 'assistant (reasoning)',
    assistant_reasoning_summary: 'assistant (reasoning summary)',
  }

  const roleClass = (role) => {
    if (role === 'user') return 'message-bubble user'
    if (role === 'assistant') return 'message-bubble assistant'
    if (role === 'tool') return 'message-bubble tool'
    if (role?.startsWith('assistant_reasoning')) return 'message-bubble reasoning'
    return 'message-bubble'
  }

  function handleToolEvent(evt) {
    const label = toolLabelFromEvent(evt?.event_type, evt?.details)
    const status = (evt?.event_type || '').toLowerCase()
    if (/completed|failed|result/.test(status)) {
      setToolActivity(null)
      if (label) {
        appendToolMessage(`${label} ${status.includes('failed') ? 'failed' : 'completed'}`)
        appendDebugEvent({
          kind: 'tool',
          eventType: evt.event_type,
          details: evt.details,
          note: 'completed',
          timestamp: Date.now(),
        })
      }
      return
    }
    if (label) {
      setToolActivity({ label, details: evt?.details })
      appendToolMessage(`${label} started${evt?.details?.query ? ` · ${evt.details.query}` : ''}`)
      appendDebugEvent({
        kind: 'tool',
        eventType: evt.event_type,
        details: evt.details,
        note: 'started',
        timestamp: Date.now(),
      })
    }
  }

  function appendToolMessage(text) {
    setMessages((prev) => [...prev, { role: 'tool', text }])
  }

  function appendDebugEvent(evt) {
    setDebugEvents((prev) => {
      const next = [...prev, evt]
      return next.slice(-12)
    })
  }

  function renderDebugContent(evt) {
    if (evt.kind === 'reasoning') {
      const snippet = (evt.delta || '').slice(0, 80)
      return `(${evt.variant}) ${snippet}${snippet.length === 80 ? '…' : ''}`
    }
    if (evt.kind === 'tool') {
      const name = evt.details?.tool || evt.details?.server_label || evt.eventType || 'tool'
      const info = evt.details?.query || evt.details?.input || ''
      return `${name} ${evt.note || ''} ${info}`.trim()
    }
    if (evt.kind === 'draft') {
      const snippet = (evt.markdown || '').slice(0, 80)
      return `draft:${evt.section || 'main'} ${snippet}${snippet.length === 80 ? '…' : ''}`
    }
    return JSON.stringify(evt)
  }

  function toolLabelFromEvent(eventType, details) {
    const lowerType = (eventType || '').toLowerCase()
    const tip =
      details?.tool ||
      details?.tool_name ||
      details?.server_label ||
      details?.name ||
      ''
    if (lowerType.includes('web_search') || tip.toLowerCase().includes('web_search')) {
      const query = details?.query || details?.input || ''
      return query ? `Web search · ${query}` : 'Web search'
    }
    if (tip) return tip
    if (lowerType.includes('mcp')) return 'External tool'
    return null
  }

  return (
    <div className="app-shell">
      <div className="glow glow-one" aria-hidden="true" />
      <div className="glow glow-two" aria-hidden="true" />

      <header className="app-header">
        <div>
          <p className="eyebrow">WILL-IT — Sharper wills with an on-call copilot</p>
          <p className="lede">Stream answers, drop evidence, and watch the assistant reason through every requirement.</p>
        </div>
        <button className="ghost-button" onClick={triggerUpload}>
          Attach evidence
        </button>
      </header>

      <main className="workspace" style={{ gridTemplateColumns: `minmax(320px, 1fr) 12px ${Math.max(200, draftWidth)}px` }}>
        <section className="conversation-card" style={{ height: `${chatHeight}px` }}>
          <div className="card-header">
            <div>
              <h2>Conversation</h2>
              <p className="muted">Session {session?.id?.slice(0, 8) || 'pending'} · Cmd/Ctrl + Enter to send</p>
              {toolActivity && (
                <div className="tool-indicator">
                  <span className="tool-spark" />
                  <span>{toolActivity.label}</span>
                </div>
              )}
            </div>
            <div className="card-actions">
              <input ref={fileInputRef} className="hidden-file" type="file" multiple onChange={onUpload} />
              <button className="ghost-button subtle" onClick={triggerUpload}>
                Add files
              </button>
              <button className="primary-button" onClick={send}>
                Send
              </button>
            </div>
          </div>

          <div className="mode-toggle">
            <span className="muted">Mode:</span>
            <div className="mode-buttons">
              <button
                className={`mode-button ${mode === 'fast' ? 'active' : ''}`}
                onClick={() => setMode('fast')}
              >
                ⚡ Fast (no search)
              </button>
              <button
                className={`mode-button ${mode === 'research' ? 'active' : ''}`}
                onClick={() => setMode('research')}
              >
                🔍 Research (search + reasoning)
              </button>
            </div>
          </div>

          <div className="message-scroll-container">
            <div
              className="message-scroll"
              ref={messageScrollRef}
              onScroll={(e) => {
                const el = e.currentTarget
                const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 60
                setAutoScroll(nearBottom)
              }}
            >
              {messages.length === 0 && (
                <div className="empty-state">
                  <p>Ask anything about probate rules, upload prior wills, or paste tricky scenarios to get started.</p>
                </div>
              )}
            {messages.map((m, i) => (
              <div key={i} className={roleClass(m.role)}>
                <div className="message-role">{roleLabel[m.role] || m.role}</div>
                <div className="message-text">{m.text}</div>
              </div>
            ))}
              {reasoningActive && (
                <div className="reasoning-indicator">
                  <div className="ping" style={{ opacity: 0.4 + 0.15 * reasoningDots }} />
                  <span>Assistant is reasoning{'.'.repeat(reasoningDots)}</span>
                </div>
              )}
            </div>
            {!autoScroll && (
              <button
                className="jump-latest"
                onClick={() => {
                  if (messageScrollRef.current) {
                    messageScrollRef.current.scrollTop = messageScrollRef.current.scrollHeight
                  }
                  setAutoScroll(true)
                }}
              >
                Jump to latest
              </button>
            )}
          </div>

          <div className="composer">
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                  e.preventDefault()
                  send()
                }
              }}
              placeholder="Ask about witness rules, guardians, or reference uploaded text…"
              rows={3}
              className="composer-textarea"
            />
            <div className="composer-footer">
              <button className="ghost-button subtle" onClick={triggerUpload}>
                Upload
              </button>
              <span className="hint">Cmd/Ctrl + Enter</span>
              <button className="primary-button" onClick={send}>
                Send
              </button>
            </div>
          </div>
        </section>

        <div
          className={`resize-handle ${resizing ? 'active' : ''}`}
          onMouseDown={() => setResizing(true)}
        >
          <span />
        </div>

        <aside className="insight-panel" style={{ width: `${draftWidth}px` }}>
          <div className="draft-card">
            <div className="draft-card-header">
              <div>
                <h3>Draft</h3>
                <p className="muted">Model updates appear here via the Drafter tool.</p>
              </div>
              <div className="draft-card-actions">
                <div className="zoom-buttons">
                  <button className="ghost-button subtle" onClick={() => setDraftZoom((z) => Math.max(0.6, z - 0.1))}>
                    −
                  </button>
                  <button className="ghost-button subtle" onClick={() => setDraftZoom((z) => Math.min(1.5, z + 0.1))}>
                    +
                  </button>
                </div>
                {Object.keys(draftSections).length > 0 && (
                  <button className="ghost-button subtle" onClick={() => setDraftSections({})}>
                    Clear
                  </button>
                )}
              </div>
            </div>
            {Object.keys(draftSections).length === 0 ? (
              <p className="muted">No draft content yet. The assistant will fill this panel when it calls the Drafter tool.</p>
            ) : (
              <div className="draft-doc" style={{ fontSize: `${draftZoom}rem` }}>
                {Object.entries(draftSections).map(([key, value]) => (
                  <section key={key}>
                    <h4>{value.title || key}</h4>
                    <div
                      className="draft-markdown"
                      dangerouslySetInnerHTML={{ __html: toSimpleHtml(value.markdown || '') }}
                    />
                  </section>
                ))}
              </div>
            )}
          </div>
          <div className="insight-card">
            <h3>Reasoning feed</h3>
            {reasoningFeed.length === 0 && !reasoningActive && <p className="muted">The assistant’s chain-of-thought will appear here when available.</p>}
            <div
              className="reasoning-feed"
              ref={reasoningScrollRef}
              onScroll={(e) => {
                const el = e.currentTarget
                const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40
                setReasoningAutoScroll(nearBottom)
              }}
            >
              {reasoningFeed.map((m, i) => (
                <div key={i} className="chip">
                  <span className="chip-label">{roleLabel[m.role] || m.role}</span>
                  <p>{m.text}</p>
                </div>
              ))}
              {reasoningActive && <p className="muted">Analyzing… stay tuned.</p>}
            </div>
            {!reasoningAutoScroll && reasoningFeed.length > 0 && (
              <button
                className="ghost-button subtle"
                onClick={() => {
                  if (reasoningScrollRef.current) {
                    reasoningScrollRef.current.scrollTop = reasoningScrollRef.current.scrollHeight
                  }
                  setReasoningAutoScroll(true)
                }}
              >
                Jump to latest
              </button>
            )}
          </div>
          <div className="insight-card">
            <h3>Session tools</h3>
            <ul>
              <li>Drag & drop PDFs, DOCX, or screenshots.</li>
              <li>Biomarkers keep every citation intact.</li>
              <li>Draft mode + audio streaming land next.</li>
            </ul>
          </div>
          <div className="insight-card">
            <h3>Debug stream</h3>
            {debugEvents.length === 0 && <p className="muted">Tool + reasoning events will appear here.</p>}
            <div className="debug-scroll">
              {debugEvents.map((evt, idx) => (
                <div key={idx} className="debug-line">
                  <span className="debug-tag">{evt.kind}</span>
                  <code>{renderDebugContent(evt)}</code>
                </div>
              ))}
            </div>
          </div>
        </aside>
      </main>
      <div className={`chat-resize-handle ${chatResizing ? 'active' : ''}`} onMouseDown={() => setChatResizing(true)}>
        <span />
      </div>
    </div>
  )
}

function toSimpleHtml(markdown = '') {
  // very lightweight markdown rendering (bold + line breaks + bullet dashes)
  let html = markdown
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
  html = html.replace(/^- (.+)$/gm, '<li>$1</li>')
  html = html.replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>')
  html = html.replace(/\n{2,}/g, '<br/><br/>').replace(/\n/g, '<br/>')
  return html
}
