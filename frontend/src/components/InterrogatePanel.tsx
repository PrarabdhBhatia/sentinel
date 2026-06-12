import { useState } from 'react'
import { GlassCard } from './GlassCard'

/**
 * D10 — "Interrogate the market" (Thesys C1 / OpenUI).
 *
 * Question in → generative UI out. The model (literal Thesys C1 when the key is
 * set, premium chat() otherwise) returns a constrained WIDGET spec; this panel
 * renders those widgets with Sentinel's own glass primitives. Per the §4 design
 * contract, generated content renders INSIDE our design language and can never
 * define it — there is no foreign stylesheet to clash. One contained card.
 */

type Tone = 'good' | 'warn' | 'bad' | 'neutral'

interface MetricWidget { type: 'metric'; label: string; value: string; tone?: Tone }
interface BarRow { label: string; value: number; display?: string; tone?: Tone }
interface BarWidget { type: 'bar'; title?: string; rows: BarRow[] }
interface TableWidget { type: 'table'; columns: string[]; rows: string[][] }
interface VerdictItem { vendor: string; claim: string; verdict: string }
interface VerdictListWidget { type: 'verdict_list'; title?: string; items: VerdictItem[] }
type Widget = MetricWidget | BarWidget | TableWidget | VerdictListWidget

interface InterrogateResponse {
  answer: string
  widgets: Widget[]
  engine?: 'c1' | 'premium'
}

const TONE_COLOR: Record<Tone, string> = {
  good: 'var(--verdict-good)',
  warn: 'var(--verdict-warn)',
  bad: 'var(--verdict-bad)',
  neutral: 'var(--text-2)',
}

const VERDICT_COLOR: Record<string, string> = {
  'Publicly substantiated': 'var(--verdict-good)',
  'Self-reported only': 'var(--verdict-warn)',
  'No public receipt': 'var(--verdict-bad)',
}

const SUGGESTIONS = [
  'Which vendor is most publicly substantiated?',
  'Rank vendors by claim inflation',
  'Which claims are self-reported only?',
]

function MetricBlock({ w }: { w: MetricWidget }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'baseline', justifyContent: 'space-between',
      gap: 12, padding: '10px 0', borderBottom: '1px solid var(--border)',
    }}>
      <span style={{ fontSize: 12, color: 'var(--muted)' }}>{w.label}</span>
      <span style={{
        fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 18,
        fontVariantNumeric: 'tabular-nums',
        color: TONE_COLOR[w.tone ?? 'neutral'],
      }}>{w.value}</span>
    </div>
  )
}

function BarBlock({ w }: { w: BarWidget }) {
  const max = Math.max(1, ...w.rows.map(r => r.value))
  return (
    <div style={{ padding: '6px 0' }}>
      {w.title && <div style={labelStyle}>{w.title}</div>}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 4 }}>
        {w.rows.map((r, i) => (
          <div key={i}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
              <span style={{ fontSize: 12, color: 'var(--text)' }}>{r.label}</span>
              <span style={{
                fontSize: 12, fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums',
                color: TONE_COLOR[r.tone ?? 'neutral'],
              }}>{r.display ?? r.value}</span>
            </div>
            <div style={{ height: 4, background: 'rgba(255,255,255,0.08)', borderRadius: 4, overflow: 'hidden' }}>
              <div style={{
                height: '100%', width: `${Math.max(2, (r.value / max) * 100)}%`,
                background: TONE_COLOR[r.tone ?? 'neutral'], opacity: 0.75,
                transition: 'width 0.6s ease',
              }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function TableBlock({ w }: { w: TableWidget }) {
  return (
    <div style={{ padding: '6px 0', overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
        <thead>
          <tr>
            {w.columns.map((c, i) => (
              <th key={i} style={{
                textAlign: 'left', padding: '6px 8px', color: 'var(--muted)',
                fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em',
                fontSize: 10, borderBottom: '1px solid var(--border)',
              }}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {w.rows.map((row, ri) => (
            <tr key={ri}>
              {row.map((cell, ci) => (
                <td key={ci} style={{
                  padding: '7px 8px', color: ci === 0 ? 'var(--text)' : 'var(--text-2)',
                  borderBottom: '1px solid var(--border)',
                  fontFamily: ci === 0 ? 'var(--font-sans)' : 'var(--font-mono)',
                  fontVariantNumeric: 'tabular-nums',
                }}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function VerdictListBlock({ w }: { w: VerdictListWidget }) {
  return (
    <div style={{ padding: '6px 0' }}>
      {w.title && <div style={labelStyle}>{w.title}</div>}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 4 }}>
        {w.items.map((it, i) => (
          <div key={i} style={{
            padding: '10px 12px', background: 'var(--surface-2)', borderRadius: 10,
            border: '1px solid var(--border)',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'baseline' }}>
              <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>{it.vendor}</span>
              <span style={{
                fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em',
                color: VERDICT_COLOR[it.verdict] ?? 'var(--muted)', whiteSpace: 'nowrap',
              }}>{it.verdict}</span>
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-2)', marginTop: 4, lineHeight: 1.4 }}>{it.claim}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

const labelStyle: React.CSSProperties = {
  fontSize: 10, color: 'var(--muted)', fontWeight: 600,
  textTransform: 'uppercase', letterSpacing: '0.1em',
}

function renderWidget(w: Widget, i: number) {
  switch (w.type) {
    case 'metric': return <MetricBlock key={i} w={w} />
    case 'bar': return <BarBlock key={i} w={w} />
    case 'table': return <TableBlock key={i} w={w} />
    case 'verdict_list': return <VerdictListBlock key={i} w={w} />
    default: return null
  }
}

export function InterrogatePanel({ marketData }: { marketData: unknown }) {
  const apiBase = (((import.meta as unknown as { env?: { VITE_API_URL?: string } }).env?.VITE_API_URL) || '').replace(/\/+$/, '')
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<InterrogateResponse | null>(null)

  const ask = async (q: string) => {
    const query = q.trim()
    if (!query || loading || !marketData) return
    setLoading(true); setError(''); setResult(null)
    try {
      const res = await fetch(`${apiBase}/interrogate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: query, market: marketData }),
      })
      if (!res.ok) { setError('Could not reach the analyst.'); return }
      setResult(await res.json() as InterrogateResponse)
    } catch {
      setError('Could not reach the analyst.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <GlassCard padding="20px 22px" style={{ marginTop: 16 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 12, gap: 12 }}>
        <div>
          <div style={labelStyle}>Interrogate the market</div>
          <div style={{ fontSize: 16, fontWeight: 700, letterSpacing: '-0.02em', color: 'var(--text)', marginTop: 3 }}>
            Ask the audit a question
          </div>
        </div>
        {result?.engine && (
          <span title="Generative UI engine" style={{
            fontSize: 10, color: 'var(--accent)', fontFamily: 'var(--font-mono)',
            background: 'var(--accent-soft)', padding: '2px 8px', borderRadius: 9999,
          }}>{result.engine === 'c1' ? 'Thesys C1' : 'C1 (premium fallback)'}</span>
        )}
      </div>

      <div style={{ display: 'flex', gap: 8 }}>
        <input
          value={question}
          onChange={e => setQuestion(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') ask(question) }}
          placeholder="Which vendor has the most substantiated claims?"
          style={{
            flex: 1, boxSizing: 'border-box',
            background: 'rgba(255,255,255,0.05)', border: '1px solid var(--border)',
            borderRadius: 12, color: 'var(--text)', fontSize: 13,
            fontFamily: 'var(--font-sans)', padding: '11px 14px', outline: 'none',
          }}
        />
        <button onClick={() => ask(question)} disabled={loading || !question.trim()} className="pill pill-primary"
          style={{ height: 'auto', fontSize: 13, padding: '0 18px' }}>
          {loading ? 'Thinking…' : 'Ask'}
        </button>
      </div>

      {!result && !loading && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 10 }}>
          {SUGGESTIONS.map(s => (
            <button key={s} onClick={() => { setQuestion(s); ask(s) }} className="pill"
              style={{ height: 28, fontSize: 11, padding: '0 12px' }}>{s}</button>
          ))}
        </div>
      )}

      {error && <div style={{ color: 'var(--verdict-bad)', fontSize: 12, marginTop: 12 }}>{error}</div>}

      {result && (
        <div style={{ marginTop: 16 }}>
          {result.answer && (
            <div style={{
              fontSize: 14, color: 'var(--text)', lineHeight: 1.55, marginBottom: 14,
              fontFamily: 'var(--font-serif)',
            }}>{result.answer}</div>
          )}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {result.widgets?.map(renderWidget)}
          </div>
        </div>
      )}
    </GlassCard>
  )
}
