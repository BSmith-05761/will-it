import React, { useEffect, useRef, useState, useLayoutEffect } from 'react'
import './App.css'

const chunkTextForSpeech = (text, maxChars = 1400, minChars = 600) => {
  if (!text) return []
  if (text.length <= maxChars) return [text]
  const chunks = []
  let start = 0
  const total = text.length
  while (start < total) {
    let end = Math.min(start + maxChars, total)
    if (end >= total) {
      chunks.push(text.slice(start))
      break
    }
    const searchFloor = Math.min(start + minChars, end)
    let splitPos = -1
    for (let i = end; i > searchFloor; i -= 1) {
      if (text[i - 1] === '\n') {
        splitPos = i
        break
      }
    }
    if (splitPos === -1) {
      for (let i = end; i > searchFloor; i -= 1) {
        if (text[i - 1] === ' ') {
          splitPos = i
          break
        }
      }
    }
    if (splitPos === -1 || splitPos <= start) {
      splitPos = end
    }
    chunks.push(text.slice(start, splitPos))
    start = splitPos
  }
  return chunks
}

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
  const [isRecording, setIsRecording] = useState(false)
  const [voiceBusy, setVoiceBusy] = useState(false)
  const [voiceError, setVoiceError] = useState(null)
  const [voiceAutoSend, setVoiceAutoSend] = useState(false)
  const [voiceTranscript, setVoiceTranscript] = useState('')
  const [voicePlaying, setVoicePlaying] = useState(false)
  const [voicePaused, setVoicePaused] = useState(false)
  const [readResponses, setReadResponses] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [uploadedFiles, setUploadedFiles] = useState([])
  const [showUploads, setShowUploads] = useState(false)
  const [activeUploadId, setActiveUploadId] = useState(null)
  const [assistantThinking, setAssistantThinking] = useState(false)
  const wsRef = useRef(null)
  const fileInputRef = useRef(null)
  const messageScrollRef = useRef(null)
  const reasoningScrollRef = useRef(null)
  const mediaRecorderRef = useRef(null)
  const recordedChunksRef = useRef([])
  const audioRef = useRef(typeof Audio !== 'undefined' ? new Audio() : null)
  const voiceQueueRef = useRef([])
  const requestTTSRef = useRef(null)
  const readResponsesRef = useRef(true)
  const ttsRunIdRef = useRef(0)
  const activeUpload = uploadedFiles.find((file) => file.id === activeUploadId) || null

  useEffect(() => {
    if (!reasoningActive) {
      setReasoningDots(0)
      return
    }
    const timer = setInterval(() => setReasoningDots((d) => (d + 1) % 4), 360)
    return () => clearInterval(timer)
  }, [reasoningActive])

  useEffect(() => {
    readResponsesRef.current = readResponses
  }, [readResponses])

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
    return () => {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop()
      }
      if (audioRef.current) {
        audioRef.current.pause()
        audioRef.current.src = ''
      }
    }
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
          setAssistantThinking(false)
          applyStreamDelta('assistant', msg.text_delta || '', msg.full_text)
        } else if (msg.type === 'assistant_reasoning_delta') {
          setAssistantThinking(false)
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
          setAssistantThinking(false)
          setMessages((prev) => [...prev, { role: 'tool', text: `Error: ${msg.message || msg.code}` }])
        } else if (msg.type === 'assistant_complete') {
          setAssistantThinking(false)
          if (readResponsesRef.current && requestTTSRef.current) {
            requestTTSRef.current(msg.text)
          }
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

  const sendMessage = (content) => {
    const t = content.trim()
    if (!t || !wsRef.current) return
    setMessages((prev) => [...prev, { role: 'user', text: t, meta: { mode } }])
    wsRef.current.send(JSON.stringify({ type: 'user_message', text: t, mode }))
    setText('')
    setVoiceTranscript('')
    setAssistantThinking(true)
  }

  const send = () => sendMessage(text)

  const onUpload = async (e) => {
    const files = Array.from(e.target.files || [])
    if (files.length === 0) return
    const fd = new FormData()
    for (const f of files) fd.append('files', f)
    const sid = session?.id ? encodeURIComponent(session.id) : 'default'
    setUploading(true)
    try {
      const res = await fetch(`${backend}/api/uploads?session_id=${sid}`, { method: 'POST', body: fd })
      if (!res.ok) throw new Error(`Upload failed (${res.status})`)
      const json = await res.json()
      const docList = Array.isArray(json?.documents) ? json.documents : []
      const uploadStamp = new Date().toLocaleString()
      const summaries = docList.map((doc, idx) => ({
        id: `${Date.now()}-${idx}-${doc?.name || doc?.filename || 'doc'}`,
        name: doc?.name || doc?.filename || `Document ${idx + 1}`,
        mode: doc?.mode || 'text',
        uploadedAt: uploadStamp,
        textPreview: doc?.text_block || '',
        imageBase64: doc?.image_base64 || '',
        mimeType: doc?.mime_type || '',
      }))
      setUploadedFiles((prev) => [...summaries, ...prev])
      if (summaries.length > 0) {
        setShowUploads(true)
        setActiveUploadId(summaries[0].id)
      }
      setMessages((prev) => [
        ...prev,
        {
          role: 'tool',
          text: 'Upload processed: ' + (json?.documents?.map((d) => `${d.name} (${d.mode})`).join(', ') || ''),
        },
      ])
    } catch (err) {
      console.error(err)
      setMessages((prev) => [...prev, { role: 'tool', text: 'Upload failed. Please try again.' }])
    } finally {
      setUploading(false)
      if (e?.target) {
        e.target.value = ''
      }
    }
  }

  const triggerUpload = () => fileInputRef.current?.click()

  const uploadVoiceBlob = async (blob) => {
    if (!blob || blob.size === 0) return
    setVoiceBusy(true)
    setVoiceError(null)
    try {
      const fd = new FormData()
      fd.append('audio', blob, 'voice.webm')
      const res = await fetch(`${backend}/api/voice-query`, { method: 'POST', body: fd })
      if (!res.ok) throw new Error(`Voice query failed (${res.status})`)
      const data = await res.json()
      if (data?.transcript) {
        if (voiceAutoSend) {
          sendMessage(data.transcript)
          setVoiceTranscript('')
        } else {
          setVoiceTranscript(data.transcript)
          setText(data.transcript)
        }
      }
    } catch (err) {
      console.error(err)
      setVoiceError('Voice request failed. Please try again.')
    } finally {
      setVoiceBusy(false)
    }
  }

  const enqueueAudio = (base64) => {
    if (!base64) return
    voiceQueueRef.current.push(base64)
    playNextAudio()
  }

  const playNextAudio = async () => {
    if (!audioRef.current) return
    if (voicePlaying || voicePaused || !voiceQueueRef.current.length) return
    const next = voiceQueueRef.current.shift()
    audioRef.current.src = `data:audio/mp3;base64,${next}`
    setVoicePlaying(true)
    setVoicePaused(false)
    audioRef.current.onended = () => {
      setVoicePlaying(false)
      setVoicePaused(false)
      playNextAudio()
    }
    try {
      await audioRef.current.play()
    } catch (err) {
      console.error(err)
      setVoicePlaying(false)
      playNextAudio()
    }
  }

  const cancelPendingAudio = () => {
    ttsRunIdRef.current += 1
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.currentTime = 0
    }
    voiceQueueRef.current = []
    setVoicePlaying(false)
    setVoicePaused(false)
  }

  const requestTTS = async (text) => {
    const trimmed = text?.trim()
    if (!trimmed) return
    cancelPendingAudio()
    setVoiceError(null)
    const runId = ttsRunIdRef.current
    const chunks = chunkTextForSpeech(trimmed)
    if (!chunks.length) return
    for (const chunk of chunks) {
      if (ttsRunIdRef.current !== runId) break
      try {
        const res = await fetch(`${backend}/api/tts`, {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ text: chunk }),
        })
        if (!res.ok) throw new Error('tts failed')
        const data = await res.json()
        if (ttsRunIdRef.current !== runId) break
        if (!data?.audio_base64) continue
        enqueueAudio(data.audio_base64)
      } catch (err) {
        if (ttsRunIdRef.current !== runId) break
        console.error(err)
        setVoiceError('Unable to play voice reply.')
        break
      }
    }
  }

  useEffect(() => {
    requestTTSRef.current = requestTTS
  }, [requestTTS])

  const stopVoicePlayback = () => {
    cancelPendingAudio()
  }

  const pauseVoicePlayback = () => {
    if (!audioRef.current) return
    if (!voicePlaying || voicePaused) return
    audioRef.current.pause()
    setVoicePaused(true)
  }

  const resumeVoicePlayback = async () => {
    if (!audioRef.current) return
    if (!voicePlaying || !voicePaused) return
    try {
      await audioRef.current.play()
      setVoicePaused(false)
    } catch (err) {
      console.error(err)
      setVoiceError('Unable to resume voice playback.')
    }
  }

  const startRecording = async () => {
    if (isRecording || voiceBusy) return
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const options = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? { mimeType: 'audio/webm;codecs=opus' }
        : undefined
      const recorder = new MediaRecorder(stream, options)
      recordedChunksRef.current = []
      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          recordedChunksRef.current.push(event.data)
        }
      }
      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop())
        const blob = new Blob(recordedChunksRef.current, { type: recorder.mimeType || 'audio/webm' })
        recordedChunksRef.current = []
        uploadVoiceBlob(blob)
      }
      recorder.start()
      mediaRecorderRef.current = recorder
      setIsRecording(true)
      setVoiceError(null)
    } catch (err) {
      console.error(err)
      setVoiceError('Microphone access denied or unavailable.')
    }
  }

  const stopRecording = () => {
    if (!isRecording || !mediaRecorderRef.current) return
    mediaRecorderRef.current.stop()
    setIsRecording(false)
  }

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
              <button className="ghost-button subtle" onClick={triggerUpload} disabled={uploading}>
                Add files
              </button>
              {uploading && <span className="upload-indicator">Uploading…</span>}
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

          {(uploadedFiles.length > 0 || uploading) && (
            <div className="uploads-panel">
              <button
                className="upload-toggle"
                onClick={() => setShowUploads((s) => !s)}
              >
                <span>{showUploads ? '▾' : '▸'}</span>
                <span>Uploads ({uploadedFiles.length})</span>
                {uploading && <span className="upload-status-pill">Uploading…</span>}
              </button>
              {showUploads && (
                <>
                  <ul className="upload-list">
                    {uploadedFiles.length === 0 && !uploading && (
                      <li>
                        <span className="upload-meta">No files yet.</span>
                      </li>
                    )}
                    {uploadedFiles.map((doc) => (
                      <li
                        key={doc.id}
                        className={doc.id === activeUploadId ? 'active' : ''}
                        onClick={() => setActiveUploadId(doc.id === activeUploadId ? null : doc.id)}
                      >
                        <div>
                          <strong>{doc.name}</strong>
                          <span className="upload-meta"> · {doc.mode}</span>
                        </div>
                        <span className="upload-meta">{doc.uploadedAt}</span>
                      </li>
                    ))}
                  </ul>
                  {activeUpload && (
                    <div className="upload-preview-card">
                      <div className="upload-preview-header">
                        <h4>{activeUpload.name}</h4>
                        <button className="ghost-button subtle" onClick={() => setActiveUploadId(null)}>
                          Close
                        </button>
                      </div>
                      {activeUpload.imageBase64 ? (
                        <div className="upload-preview-body image">
                          <img
                            src={`data:${activeUpload.mimeType || 'image/png'};base64,${activeUpload.imageBase64}`}
                            alt={activeUpload.name}
                          />
                        </div>
                      ) : (
                        <pre className="upload-preview-body text">
                          {activeUpload.textPreview || 'No preview available.'}
                        </pre>
                      )}
                    </div>
                  )}
                </>
              )}
            </div>
          )}

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
              {assistantThinking && (
                <div className="assistant-thinking">
                  <div className="thinking-avatar">AI</div>
                  <div className="thinking-bubble">
                    <span>Assistant is deciding what to do…</span>
                    <span className="thinking-dots">
                      <span />
                      <span />
                      <span />
                    </span>
                  </div>
                </div>
              )}
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
              <button className="ghost-button subtle" onClick={triggerUpload} disabled={uploading}>
                Upload
              </button>
              <button className="primary-button" onClick={send}>
                Send
              </button>
            </div>
          </div>
          {voiceTranscript && (
            <div className="voice-transcript-panel">
              <p>Voice transcript captured. Review before sending:</p>
              <div className="voice-transcript-text">{voiceTranscript}</div>
              <div className="voice-transcript-actions">
                <button
                  className="primary-button"
                  onClick={() => {
                    sendMessage(voiceTranscript)
                  }}
                >
                  Send voice text
                </button>
                <button
                  className="ghost-button subtle"
                  onClick={() => {
                    setText(voiceTranscript)
                    setVoiceTranscript('')
                  }}
                >
                  Keep editing
                </button>
                <button className="ghost-button subtle" onClick={() => setVoiceTranscript('')}>
                  Clear transcript
                </button>
              </div>
            </div>
          )}
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
          <div className="voice-card">
            <div className="voice-card-header">
              <div>
                <h3>Voice controls</h3>
                <p className="muted">Record, auto-send, and manage read-back here.</p>
              </div>
              <span className="voice-status">
                {isRecording
                  ? 'Recording…'
                  : voiceBusy
                  ? 'Processing…'
                  : voicePlaying
                  ? voicePaused
                    ? 'Voice paused'
                    : 'Playing reply…'
                  : voiceTranscript
                  ? 'Transcript ready'
                  : 'Idle'}
              </span>
            </div>
            <div className="voice-toggle-list">
              <label className="toggle-control">
                <input
                  type="checkbox"
                  checked={voiceAutoSend}
                  onChange={(e) => setVoiceAutoSend(e.target.checked)}
                />
                <span className="toggle-track">
                  <span className="toggle-thumb" />
                </span>
                <span className="toggle-label">Auto-send voice</span>
              </label>
              <label className="toggle-control">
                <input
                  type="checkbox"
                  checked={readResponses}
                  onChange={(e) => setReadResponses(e.target.checked)}
                />
                <span className="toggle-track">
                  <span className="toggle-thumb" />
                </span>
                <span className="toggle-label">Read response aloud</span>
              </label>
            </div>
            <div className="voice-button-grid">
              <button
                className={`ghost-button subtle mic-button ${isRecording ? 'recording' : ''}`}
                onClick={() => {
                  if (isRecording) {
                    stopRecording()
                  } else {
                    startRecording()
                  }
                }}
                disabled={voiceBusy && !isRecording}
              >
                {isRecording ? 'Stop recording' : '🎤 Start recording'}
              </button>
              <button
                className="ghost-button subtle"
                onClick={voicePaused ? resumeVoicePlayback : pauseVoicePlayback}
                disabled={!voicePlaying}
              >
                {voicePaused ? 'Resume voice' : 'Pause voice'}
              </button>
              <button
                className="ghost-button subtle"
                onClick={stopVoicePlayback}
                disabled={!voicePlaying && !voicePaused}
              >
                Stop voice
              </button>
            </div>
            {voiceError && <p className="voice-error-inline">{voiceError}</p>}
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
