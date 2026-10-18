"use client"

import { useState } from "react"
import EventDetailModal, { type EventDetail } from "@/components/EventDetailModal"

export type EventNode = {
  id: string
  name: string
  category: string | null
  type: string | null
  subtype: string | null
  timestamp: string
  agentName: string
  run_id: string
  span_id: string | null
  iteration_id: number | null
  input: unknown
  output: unknown
  metadata: unknown
  error: unknown
}

export type SpanNode = {
  id: string
  spanName: string | null
  startTime: string | null
  events: EventNode[]
  children: SpanNode[]
}

export type RunGroup = {
  runId: string
  agentName: string
  rootSpans: SpanNode[]
  rootEvents: EventNode[]
}

function fmt(ts: string) {
  return new Date(ts).toLocaleString(undefined, {
    month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  })
}

function CategoryBadge({ category }: { category: string | null }) {
  if (!category) return <span style={{ color: "var(--text-muted)" }}>—</span>
  return (
    <span style={{
      padding: "0.2rem 0.55rem", borderRadius: 6,
      background: "var(--sidebar-active-bg)",
      color: "var(--accent)", fontSize: 12, fontWeight: 500,
      whiteSpace: "nowrap",
    }}>
      {category}
    </span>
  )
}

function EventRow({ event, onSelect }: { event: EventNode; onSelect: (e: EventNode) => void }) {
  return (
    <div
      onClick={() => onSelect(event)}
      style={{
        display: "grid",
        gridTemplateColumns: "160px 120px 1fr auto",
        alignItems: "center",
        gap: "0.5rem",
        padding: "0.45rem 0.75rem",
        borderTop: "1px solid var(--card-border)",
        cursor: "pointer",
        transition: "background 0.1s",
      }}
      onMouseEnter={e => (e.currentTarget.style.background = "var(--sidebar-active-bg)")}
      onMouseLeave={e => (e.currentTarget.style.background = "")}
    >
      <span style={{ color: "var(--text-muted)", fontSize: 12, whiteSpace: "nowrap", fontVariantNumeric: "tabular-nums" }}>
        {fmt(event.timestamp)}
      </span>
      <span style={{ color: "var(--main-text)", fontSize: 13 }}>
        {event.agentName}
      </span>
      <span style={{ color: "var(--main-text)", fontFamily: "monospace", fontSize: 13 }}>
        {event.name}
      </span>
      <CategoryBadge category={event.category} />
    </div>
  )
}

function SpanBlock({ node, onSelect }: { node: SpanNode; onSelect: (e: EventNode) => void }) {
  const [open, setOpen] = useState(false)
  const hasChildren = node.events.length > 0 || node.children.length > 0

  return (
    <div style={{
      border: "1px solid var(--card-border)",
      borderRadius: 8,
      overflow: "hidden",
    }}>
      <div style={{
        display: "flex",
        alignItems: "center",
        gap: "0.6rem",
        padding: "0.45rem 0.75rem",
        background: "var(--card-bg)",
      }}>
        {hasChildren ? (
          <button
            onClick={() => setOpen(o => !o)}
            style={{
              width: 18, height: 18, borderRadius: 4,
              border: "1px solid var(--card-border)",
              background: "var(--main-bg)", color: "var(--text-muted)",
              fontSize: 12, fontWeight: 700, cursor: "pointer",
              display: "flex", alignItems: "center", justifyContent: "center",
              flexShrink: 0, lineHeight: 1,
            }}
          >
            {open ? "−" : "+"}
          </button>
        ) : (
          <span style={{ width: 18, flexShrink: 0 }} />
        )}
        <span style={{ color: "var(--text-muted)", fontSize: 12, whiteSpace: "nowrap", fontVariantNumeric: "tabular-nums" }}>
          {node.startTime ? fmt(node.startTime) : "—"}
        </span>
        <span style={{ fontFamily: "monospace", fontSize: 12, color: "var(--text-muted)", marginLeft: "auto" }}>
          {node.spanName ?? "span"}
        </span>
      </div>

      {open && hasChildren && (
        <div style={{
          paddingLeft: 12, paddingRight: 6, paddingBottom: 6,
          background: "var(--main-bg)",
          display: "flex", flexDirection: "column", gap: 6,
        }}>
          {node.events.map(e => <EventRow key={e.id} event={e} onSelect={onSelect} />)}
          {node.children.map(c => <SpanBlock key={c.id} node={c} onSelect={onSelect} />)}
        </div>
      )}
    </div>
  )
}

export default function EventTree({ groups }: { groups: RunGroup[] }) {
  const [selected, setSelected] = useState<EventNode | null>(null)

  if (groups.length === 0) {
    return (
      <div style={{
        background: "var(--card-bg)", border: "1px solid var(--card-border)",
        borderRadius: 12, padding: "3rem", textAlign: "center", color: "var(--text-muted)",
        fontSize: 13,
      }}>
        No events found
      </div>
    )
  }

  return (
    <>
      <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        {groups.map(group => (
          <div key={group.runId} style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {group.rootSpans.map(s => <SpanBlock key={s.id} node={s} onSelect={setSelected} />)}
            {group.rootEvents.map(e => (
              <div key={e.id} style={{
                background: "var(--card-bg)", border: "1px solid var(--card-border)", borderRadius: 8,
              }}>
                <EventRow event={e} onSelect={setSelected} />
              </div>
            ))}
          </div>
        ))}
      </div>

      {selected && (
        <EventDetailModal
          event={selected as EventDetail}
          onClose={() => setSelected(null)}
        />
      )}
    </>
  )
}
