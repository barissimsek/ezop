"use client"

import { useState, useMemo } from "react"
import type { Agent, AgentRun, RunEvent } from "@/app/dashboard/agents/actions"
import { listRunEvents } from "@/app/dashboard/agents/actions"


// ─── Helpers ──────────────────────────────────────────────────────────────────

function relativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diffMs / 60000)
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

function successColor(rate: number): string {
  if (rate >= 90) return "#10B981"
  if (rate >= 70) return "#F59E0B"
  return "#EF4444"
}

const STATUS_COLOR: Record<Agent["status"], string> = {
  active: "#10B981",
  paused: "#F59E0B",
  failed: "#EF4444",
}

const RUN_STATUS_COLOR: Record<AgentRun["status"], string> = {
  success:   "#10B981",
  failed:    "#EF4444",
  partial:   "#F59E0B",
  running:   "#06B6D4",
  cancelled: "#6B7280",
}


// ─── Tab sub-components ───────────────────────────────────────────────────────

function OverviewTab({ agent }: { agent: Agent }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <p style={{ fontSize: 13, color: "var(--main-text)", lineHeight: 1.6 }}>{agent.description}</p>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
        {[
          ["Owner", agent.owner],
          ["Runtime", agent.runtime],
          ["Created", "Jan 5, 2026"],
          ["Status", agent.status],
        ].map(([label, value]) => (
          <div key={label} style={{ fontSize: 12 }}>
            <div style={{ color: "var(--text-muted)", marginBottom: 2 }}>{label}</div>
            <div style={{ color: "var(--main-text)", fontWeight: 500 }}>{value}</div>
          </div>
        ))}
      </div>

      <div>
        <div style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-muted)", marginBottom: "0.5rem" }}>Versions</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {agent.versions.map(v => (
            <div key={v.version} style={{
              padding: "0.6rem 0.75rem", borderRadius: 8,
              border: `1px solid ${v.version === agent.currentVersion ? "var(--accent)" : "var(--card-border)"}`,
              background: v.version === agent.currentVersion ? "var(--sidebar-active-bg)" : "transparent",
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 3 }}>
                <span style={{ fontFamily: "monospace", fontSize: 12, fontWeight: 600, color: v.version === agent.currentVersion ? "var(--accent)" : "var(--main-text)" }}>
                  {v.version}{v.version === agent.currentVersion ? " · current" : ""}
                </span>
                <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{new Date(v.createdAt).toLocaleDateString()}</span>
              </div>
              <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{v.changelog}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function SpanTree({ events }: { events: RunEvent[] }) {
  // Build span → events map and span → children map
  const spanEvents = useMemo(() => {
    const map: Record<string, RunEvent[]> = {}
    for (const e of events) {
      const key = e.spanId ?? "__root__"
      ;(map[key] ??= []).push(e)
    }
    return map
  }, [events])

  // Collect all unique span ids (excluding root)
  const spanIds = useMemo(() => {
    const ids = new Set<string>()
    for (const e of events) if (e.spanId) ids.add(e.spanId)
    return [...ids]
  }, [events])

  // Build parent → children map for spans
  const spanChildren = useMemo(() => {
    const map: Record<string, string[]> = {}
    for (const e of events) {
      if (!e.spanId) continue
      const parent = e.parentSpanId ?? "__root__"
      ;(map[parent] ??= []).push(e.spanId)
    }
    // Deduplicate children lists
    for (const k of Object.keys(map)) map[k] = [...new Set(map[k])]
    return map
  }, [events])

  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({})
  const toggle = (id: string) => setCollapsed(p => ({ ...p, [id]: !p[id] }))

  function renderEvent(e: RunEvent) {
    return (
      <div key={e.id} style={{ display: "flex", gap: 10, alignItems: "flex-start", padding: "5px 0", borderBottom: "1px solid var(--card-border)" }}>
        <div style={{ marginTop: 4, width: 6, height: 6, borderRadius: "50%", background: "#6B7280", flexShrink: 0 }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
            <span style={{ fontSize: 12, fontWeight: 500, color: "var(--main-text)" }}>{e.name}</span>
            {e.category && (
              <span style={{ fontSize: 10, padding: "1px 5px", borderRadius: 4, background: "var(--sidebar-active-bg)", color: "var(--text-muted)", border: "1px solid var(--card-border)" }}>{e.category}</span>
            )}
            {e.timestamp && (
              <span style={{ fontSize: 10, color: "var(--text-muted)", marginLeft: "auto", flexShrink: 0 }}>
                {new Date(e.timestamp).toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit", fractionalSecondDigits: 3 })}
              </span>
            )}
          </div>
          {!!e.error && (
            <div style={{ marginTop: 4, fontSize: 11, color: "#EF4444", fontFamily: "monospace", background: "#EF444411", padding: "3px 6px", borderRadius: 4 }}>{typeof e.error === "object" ? JSON.stringify(e.error) : String(e.error)}</div>
          )}
        </div>
      </div>
    )
  }

  function renderSpan(spanId: string, depth: number) {
    const evts = spanEvents[spanId] ?? []
    const children = spanChildren[spanId] ?? []
    const isCollapsed = collapsed[spanId]
    const shortId = spanId.length > 12 ? spanId.slice(0, 12) + "…" : spanId
    return (
      <div key={spanId} style={{ marginLeft: depth * 14, borderLeft: depth > 0 ? "2px solid var(--card-border)" : "none", paddingLeft: depth > 0 ? 10 : 0, marginTop: 6 }}>
        <button
          onClick={() => toggle(spanId)}
          style={{ display: "flex", alignItems: "center", gap: 6, background: "none", border: "none", cursor: "pointer", padding: "4px 0", width: "100%" }}
        >
          <span style={{ fontSize: 10, color: "var(--text-muted)", lineHeight: 1 }}>{isCollapsed ? "▶" : "▼"}</span>
          <span style={{ fontFamily: "monospace", fontSize: 11, color: "#06B6D4", fontWeight: 600 }}>span</span>
          <span style={{ fontFamily: "monospace", fontSize: 11, color: "var(--text-muted)" }}>{shortId}</span>
          <span style={{ fontSize: 10, color: "var(--text-muted)" }}>· {evts.length} event{evts.length !== 1 ? "s" : ""}{children.length > 0 ? `, ${children.length} child span${children.length !== 1 ? "s" : ""}` : ""}</span>
        </button>
        {!isCollapsed && (
          <div style={{ paddingTop: 2 }}>
            {evts.map(renderEvent)}
            {children.map(cid => renderSpan(cid, depth + 1))}
          </div>
        )}
      </div>
    )
  }

  const rootEvents = spanEvents["__root__"] ?? []
  const rootSpans  = spanChildren["__root__"] ?? []

  if (events.length === 0) {
    return <div style={{ padding: "1.5rem 0", textAlign: "center", color: "var(--text-muted)", fontSize: 12 }}>No events recorded for this run.</div>
  }

  return (
    <div style={{ marginTop: 4 }}>
      {rootEvents.map(renderEvent)}
      {rootSpans.map(sid => renderSpan(sid, 0))}
      {/* Spans whose parentSpanId doesn't exist in the tree (orphaned) */}
      {spanIds
        .filter(sid => !rootSpans.includes(sid) && !spanIds.some(s => (spanChildren[s] ?? []).includes(sid)))
        .map(sid => renderSpan(sid, 0))
      }
    </div>
  )
}

function RunsTab({ agent }: { agent: Agent }) {
  const [expandedRunId, setExpandedRunId] = useState<string | null>(null)
  const [runEvents, setRunEvents] = useState<Record<string, RunEvent[]>>({})
  const [loadingRunId, setLoadingRunId] = useState<string | null>(null)

  async function handleRunClick(runId: string) {
    if (expandedRunId === runId) { setExpandedRunId(null); return }
    setExpandedRunId(runId)
    if (runEvents[runId]) return // already loaded
    setLoadingRunId(runId)
    try {
      const events = await listRunEvents(runId)
      setRunEvents(prev => ({ ...prev, [runId]: events }))
    } finally {
      setLoadingRunId(null)
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 70px 60px 16px", gap: "0.5rem", fontSize: 10, color: "var(--text-muted)", paddingBottom: 6, borderBottom: "1px solid var(--card-border)" }}>
        {["Run ID", "Status", "Duration", ""].map(h => <div key={h}>{h}</div>)}
      </div>
      {agent.recentRuns.map(run => {
        const isExpanded = expandedRunId === run.id
        const isLoading  = loadingRunId === run.id
        return (
          <div key={run.id}>
            <div
              onClick={() => handleRunClick(run.id)}
              style={{
                display: "grid", gridTemplateColumns: "1fr 70px 60px 16px",
                gap: "0.5rem", padding: "0.6rem 0", borderBottom: "1px solid var(--card-border)",
                alignItems: "center", fontSize: 12, cursor: "pointer",
                background: isExpanded ? "var(--sidebar-active-bg)" : "transparent",
              }}
            >
              <div style={{ fontFamily: "monospace", color: "var(--text-muted)", fontSize: 11 }}>{run.id.slice(0, 8)}</div>
              <span style={{ display: "inline-block", padding: "2px 6px", borderRadius: 99, fontSize: 10, fontWeight: 500, background: RUN_STATUS_COLOR[run.status] + "22", color: RUN_STATUS_COLOR[run.status] }}>{run.status}</span>
              <div style={{ color: "var(--text-muted)" }}>{run.durationS}s</div>
              <div style={{ fontSize: 10, color: "var(--text-muted)" }}>{isExpanded ? "▲" : "▼"}</div>
            </div>
            {isExpanded && (
              <div style={{ padding: "0.75rem 0.5rem", borderBottom: "1px solid var(--card-border)", background: "var(--sidebar-active-bg)" }}>
                {isLoading
                  ? <div style={{ textAlign: "center", color: "var(--text-muted)", fontSize: 12, padding: "1rem 0" }}>Loading events…</div>
                  : <SpanTree events={runEvents[run.id] ?? []} />
                }
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

function ReasoningTab() {
  return (
    <div style={{ padding: "2rem 0", textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>
      No reasoning trace data available yet.
    </div>
  )
}

function VersionsTab({ agent }: { agent: Agent }) {
  if (agent.versions.length === 0) {
    return (
      <div style={{ padding: "2rem 0", textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>
        No versions recorded yet.
      </div>
    )
  }
  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      <div style={{ display: "grid", gridTemplateColumns: "80px 1fr 140px", gap: "0.5rem", fontSize: 10, color: "var(--text-muted)", paddingBottom: 6, borderBottom: "1px solid var(--card-border)" }}>
        {["Version", "Changelog", "Created At"].map(h => <div key={h}>{h}</div>)}
      </div>
      {agent.versions.map(v => (
        <div key={v.version} style={{ display: "grid", gridTemplateColumns: "80px 1fr 140px", gap: "0.5rem", padding: "0.6rem 0", borderBottom: "1px solid var(--card-border)", alignItems: "start", fontSize: 12 }}>
          <span style={{ fontFamily: "monospace", color: "var(--accent)", fontWeight: 600 }}>{v.version}</span>
          <span style={{ color: "var(--main-text)" }}>{v.changelog || <span style={{ color: "var(--text-muted)" }}>—</span>}</span>
          <span style={{ color: "var(--text-muted)", whiteSpace: "nowrap" }}>{new Date(v.createdAt).toLocaleString()}</span>
        </div>
      ))}
    </div>
  )
}

function MetricsTab({ agent }: { agent: Agent }) {
  const avgDuration = Math.round(agent.recentRuns.reduce((s, r) => s + r.durationS, 0) / agent.recentRuns.length)

  const cards = [
    { label: "Success Rate", value: `${agent.successRate}%`, color: successColor(agent.successRate) },
    { label: "Avg Duration", value: `${avgDuration}s`,        color: "#06B6D4" },
  ]

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
      {cards.map(c => (
        <div key={c.label} style={{ padding: "1rem", background: "var(--sidebar-active-bg)", borderRadius: 10, border: "1px solid var(--card-border)" }}>
          <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: "0.4rem" }}>{c.label}</div>
          <div style={{ fontSize: "1.4rem", fontWeight: 700, color: c.color, fontVariantNumeric: "tabular-nums" }}>{c.value}</div>
        </div>
      ))}
    </div>
  )
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function AgentInventory({ initialAgents }: { initialAgents: Agent[] }) {
  const [agents, setAgents] = useState<Agent[]>(initialAgents)
  const [selected, setSelected] = useState<Agent | null>(null)
  const [search, setSearch] = useState("")
  const [activeTab, setActiveTab] = useState<"overview" | "runs" | "versions" | "reasoning" | "metrics">("overview")

  // Tag state
  const [tagInput, setTagInput] = useState("")
  const [showTagInput, setShowTagInput] = useState(false)

  // Alert state
  const [alertThreshold, setAlertThreshold] = useState(80)
  const [showAlertConfig, setShowAlertConfig] = useState(false)

  const filtered = agents.filter(a => a.name.toLowerCase().includes(search.toLowerCase()))

  function toggleStatus(agentId: string) {
    setAgents(prev => prev.map(a => {
      if (a.id !== agentId) return a
      const next = a.status === "active" ? "paused" : "active"
      return { ...a, status: next as Agent["status"] }
    }))
    if (selected?.id === agentId) {
      setSelected(prev => prev ? { ...prev, status: prev.status === "active" ? "paused" : "active" } : null)
    }
  }

  function addTag(agentId: string, tag: string) {
    if (!tag.trim()) return
    setAgents(prev => prev.map(a => a.id === agentId ? { ...a, tags: [...a.tags, tag.trim()] } : a))
    if (selected?.id === agentId) {
      setSelected(prev => prev ? { ...prev, tags: [...prev.tags, tag.trim()] } : null)
    }
    setTagInput("")
    setShowTagInput(false)
  }

  function removeTag(agentId: string, tag: string) {
    setAgents(prev => prev.map(a => a.id === agentId ? { ...a, tags: a.tags.filter(t => t !== tag) } : a))
    if (selected?.id === agentId) {
      setSelected(prev => prev ? { ...prev, tags: prev.tags.filter(t => t !== tag) } : null)
    }
  }

  return (
    <div>
      {/* Agent list */}
      <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        {/* Search */}
        <input
          placeholder="Search agents..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{
            width: "100%", padding: "0.6rem 1rem",
            border: "1px solid var(--card-border)", borderRadius: 8,
            background: "var(--card-bg)", color: "var(--main-text)",
            fontSize: 14, outline: "none",
          }}
        />

        {/* Table */}
        <div style={{ background: "var(--card-bg)", border: "1px solid var(--card-border)", borderRadius: 12, overflow: "hidden" }}>
          {/* Header */}
          <div style={{
            display: "grid",
            gridTemplateColumns: "20px 1fr 70px 140px 80px 120px 80px",
            gap: "0.5rem", padding: "0.65rem 1.25rem",
            borderBottom: "1px solid var(--card-border)",
          }}>
            {["", "Agent", "Version", "Runtime", "Last Run", "Success Rate", "Runs"].map((h, i) => (
              <div key={i} style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-muted)" }}>{h}</div>
            ))}
          </div>

          {/* Rows */}
          {filtered.map(agent => {
            const isSelected = selected?.id === agent.id
            return (
              <div
                key={agent.id}
                onClick={() => { setSelected(isSelected ? null : agent); setActiveTab("overview") }}
                style={{
                  display: "grid",
                  gridTemplateColumns: "20px 1fr 70px 140px 80px 120px 80px",
                  gap: "0.5rem", padding: "0.85rem 1.25rem",
                  borderBottom: "1px solid var(--card-border)",
                  cursor: "pointer", alignItems: "center",
                  background: isSelected ? "var(--sidebar-active-bg)" : "transparent",
                  transition: "background 0.1s",
                }}
              >
                {/* Status dot */}
                <div style={{ width: 8, height: 8, borderRadius: "50%", background: STATUS_COLOR[agent.status] }} />

                {/* Name + description */}
                <div>
                  <div style={{ fontWeight: 600, fontSize: 14, color: "var(--main-text)" }}>{agent.name}</div>
                  <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{agent.description}</div>
                </div>

                {/* Version */}
                <div style={{ fontFamily: "monospace", fontSize: 12, color: "var(--text-muted)", background: "var(--sidebar-active-bg)", borderRadius: 4, padding: "2px 6px", display: "inline-block" }}>
                  {agent.currentVersion}
                </div>

                {/* Runtime */}
                <div style={{ fontSize: 12, color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{agent.runtime}</div>

                {/* Last run */}
                <div style={{ fontSize: 12, color: "var(--text-muted)" }} suppressHydrationWarning>{agent.lastRunAt ? relativeTime(agent.lastRunAt) : "—"}</div>

                {/* Success rate */}
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <div style={{ flex: 1, height: 5, background: "var(--card-border)", borderRadius: 3, overflow: "hidden" }}>
                    <div style={{ height: "100%", width: `${agent.successRate}%`, background: successColor(agent.successRate), borderRadius: 3 }} />
                  </div>
                  <span style={{ fontSize: 11, color: successColor(agent.successRate), minWidth: 32, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{agent.successRate}%</span>
                </div>

                {/* Total runs */}
                <div style={{ fontSize: 13, color: "var(--main-text)", fontVariantNumeric: "tabular-nums", textAlign: "right" }}>{agent.totalRuns.toLocaleString()}</div>
              </div>
            )
          })}
        </div>

        <div style={{ fontSize: 12, color: "var(--text-muted)", textAlign: "right" }}>
          {filtered.length} agent{filtered.length !== 1 ? "s" : ""}
        </div>
      </div>

      {/* Detail modal */}
      {selected && (
        <div
          onClick={() => setSelected(null)}
          style={{
            position: "fixed", inset: 0, zIndex: 50,
            background: "rgba(0,0,0,0.5)", backdropFilter: "blur(2px)",
            display: "flex", alignItems: "center", justifyContent: "center",
            padding: "2rem",
          }}
        >
        <div
          onClick={e => e.stopPropagation()}
          style={{
            width: "100%", maxWidth: 720,
            background: "var(--card-bg)", border: "1px solid var(--card-border)",
            borderRadius: 14, overflow: "hidden",
            maxHeight: "calc(100vh - 4rem)", overflowY: "auto", display: "flex", flexDirection: "column",
          }}
        >
          {/* Header */}
          <div style={{ padding: "1.25rem", borderBottom: "1px solid var(--card-border)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "0.75rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div style={{ width: 10, height: 10, borderRadius: "50%", background: STATUS_COLOR[selected.status], flexShrink: 0 }} />
                <span style={{ fontWeight: 700, fontSize: "1.1rem", color: "var(--main-text)" }}>{selected.name}</span>
                <span style={{ fontFamily: "monospace", fontSize: 12, color: "var(--text-muted)", background: "var(--sidebar-active-bg)", borderRadius: 4, padding: "2px 6px" }}>{selected.currentVersion}</span>
              </div>
              <button onClick={() => setSelected(null)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", fontSize: 20, lineHeight: 1, padding: 0 }}>×</button>
            </div>

            {/* Tags */}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: "0.75rem" }}>
              {selected.tags.map(tag => (
                <span key={tag} style={{ display: "inline-flex", alignItems: "center", gap: 4, padding: "2px 8px", borderRadius: 99, fontSize: 11, background: "var(--sidebar-active-bg)", color: "var(--accent)", border: "1px solid var(--card-border)" }}>
                  {tag}
                  <button onClick={e => { e.stopPropagation(); removeTag(selected.id, tag) }} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--accent)", fontSize: 12, padding: 0, lineHeight: 1 }}>×</button>
                </span>
              ))}
              {showTagInput ? (
                <input
                  autoFocus
                  value={tagInput}
                  onChange={e => setTagInput(e.target.value)}
                  onKeyDown={e => { if (e.key === "Enter") addTag(selected.id, tagInput); if (e.key === "Escape") setShowTagInput(false) }}
                  onBlur={() => { if (tagInput) addTag(selected.id, tagInput); else setShowTagInput(false) }}
                  placeholder="tag name..."
                  style={{ padding: "2px 8px", borderRadius: 99, fontSize: 11, border: "1px solid var(--accent)", background: "transparent", color: "var(--main-text)", width: 90, outline: "none" }}
                />
              ) : null}
            </div>

            {/* Actions */}
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
              <button
                onClick={() => toggleStatus(selected.id)}
                style={{ padding: "0.35rem 0.85rem", borderRadius: 6, border: `1px solid ${selected.status === "active" ? "#F59E0B" : "#10B981"}`, background: "transparent", color: selected.status === "active" ? "#F59E0B" : "#10B981", cursor: "pointer", fontSize: 12, fontWeight: 500 }}
              >
                {selected.status === "active" ? "Pause" : "Enable"}
              </button>
              <button
                onClick={() => setShowTagInput(v => !v)}
                style={{ padding: "0.35rem 0.85rem", borderRadius: 6, border: "1px solid var(--card-border)", background: "transparent", color: "var(--main-text)", cursor: "pointer", fontSize: 12, fontWeight: 500 }}
              >
                + Add Tag
              </button>
              <button
                onClick={() => setShowAlertConfig(v => !v)}
                style={{ padding: "0.35rem 0.85rem", borderRadius: 6, border: "1px solid var(--card-border)", background: "transparent", color: "var(--main-text)", cursor: "pointer", fontSize: 12, fontWeight: 500 }}
              >
                Set Alert
              </button>
            </div>

            {/* Alert config inline */}
            {showAlertConfig && (
              <div style={{ marginTop: "0.75rem", padding: "0.75rem", background: "var(--sidebar-active-bg)", borderRadius: 8, fontSize: 12, display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ color: "var(--text-muted)" }}>Alert when success rate &lt;</span>
                <input
                  type="number" min={0} max={100} value={alertThreshold}
                  onChange={e => setAlertThreshold(Number(e.target.value))}
                  style={{ width: 50, padding: "2px 6px", borderRadius: 4, border: "1px solid var(--card-border)", background: "var(--card-bg)", color: "var(--main-text)", fontSize: 12, textAlign: "center" }}
                />
                <span style={{ color: "var(--text-muted)" }}>%</span>
                <button onClick={() => setShowAlertConfig(false)} style={{ marginLeft: "auto", padding: "2px 10px", borderRadius: 4, border: "1px solid #10B981", background: "transparent", color: "#10B981", cursor: "pointer", fontSize: 11 }}>Save</button>
              </div>
            )}
          </div>

          {/* Tabs */}
          <div style={{ display: "flex", borderBottom: "1px solid var(--card-border)", overflowX: "auto" }}>
            {(["overview", "runs", "versions", "reasoning", "metrics"] as const).map(tab => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                style={{
                  padding: "0.65rem 1rem", border: "none", background: "transparent",
                  color: activeTab === tab ? "var(--accent)" : "var(--text-muted)",
                  borderBottom: activeTab === tab ? "2px solid var(--accent)" : "2px solid transparent",
                  cursor: "pointer", fontSize: 13, fontWeight: activeTab === tab ? 600 : 400,
                  whiteSpace: "nowrap", textTransform: "capitalize",
                }}
              >
                {tab === "runs" ? "Run History" : tab === "reasoning" ? "Reasoning" : tab.charAt(0).toUpperCase() + tab.slice(1)}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <div style={{ padding: "1.25rem" }}>
            {activeTab === "overview"   && <OverviewTab  agent={selected} />}
            {activeTab === "runs"       && <RunsTab      agent={selected} />}
            {activeTab === "versions"   && <VersionsTab   agent={selected} />}
            {activeTab === "reasoning"  && <ReasoningTab />}
            {activeTab === "metrics"    && <MetricsTab   agent={selected} />}
          </div>
        </div>
        </div>
      )}
    </div>
  )
}
