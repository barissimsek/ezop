"use client"

import { useState } from "react"

export type EventDetail = {
  id: string
  name: string
  category: string | null
  type: string | null
  subtype: string | null
  timestamp: string
  run_id: string
  span_id: string | null
  iteration_id: number | null
  input: unknown
  output: unknown
  metadata: unknown
  error: unknown
}

function JsonBlock({ value }: { value: unknown }) {
  if (value == null) return <span style={{ color: "var(--text-muted)", fontSize: 12 }}>—</span>
  return (
    <pre style={{
      margin: 0,
      fontSize: 12,
      lineHeight: 1.6,
      color: "var(--main-text)",
      background: "var(--main-bg)",
      border: "1px solid var(--card-border)",
      borderRadius: 8,
      padding: "0.75rem 1rem",
      overflowX: "auto",
      whiteSpace: "pre-wrap",
      wordBreak: "break-all",
      maxHeight: 300,
      overflowY: "auto",
    }}>
      {JSON.stringify(value, null, 2)}
    </pre>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <span style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.07em", color: "var(--text-muted)" }}>
        {label}
      </span>
      {children}
    </div>
  )
}

function InlineValue({ value }: { value: string | null | undefined }) {
  if (!value) return <span style={{ color: "var(--text-muted)", fontSize: 13 }}>—</span>
  return <span style={{ fontSize: 13, color: "var(--main-text)", fontFamily: "monospace" }}>{value}</span>
}

export default function EventDetailModal({
  event,
  onClose,
}: {
  event: EventDetail
  onClose: () => void
}) {
  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0,
        background: "rgba(0,0,0,0.55)",
        display: "flex", alignItems: "center", justifyContent: "center",
        zIndex: 1000,
        padding: "1.5rem",
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: "var(--card-bg)",
          border: "1px solid var(--card-border)",
          borderRadius: 14,
          padding: "1.75rem",
          width: "100%",
          maxWidth: 680,
          maxHeight: "90vh",
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
          gap: "1.25rem",
        }}
      >
        {/* Header */}
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "1rem" }}>
          <div>
            <div style={{ fontSize: "1rem", fontWeight: 700, color: "var(--main-text)", fontFamily: "monospace" }}>
              {event.name}
            </div>
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>
              {new Date(event.timestamp).toLocaleString(undefined, {
                year: "numeric", month: "short", day: "numeric",
                hour: "2-digit", minute: "2-digit", second: "2-digit",
              })}
            </div>
          </div>
          <button
            onClick={onClose}
            style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", fontSize: 22, lineHeight: 1, flexShrink: 0 }}
          >
            ×
          </button>
        </div>

        {/* Classification */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "1rem" }}>
          <Field label="Category">
            {event.category ? (
              <span style={{
                display: "inline-block", fontSize: 12, fontWeight: 600,
                padding: "0.15rem 0.55rem", borderRadius: 6,
                background: "var(--sidebar-active-bg)", color: "var(--accent)",
                width: "fit-content",
              }}>
                {event.category}
              </span>
            ) : <span style={{ color: "var(--text-muted)", fontSize: 13 }}>—</span>}
          </Field>
          <Field label="Type"><InlineValue value={event.type} /></Field>
          <Field label="Subtype"><InlineValue value={event.subtype} /></Field>
        </div>

        {/* IDs */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
          <Field label="Run ID"><InlineValue value={event.run_id} /></Field>
          <Field label="Span ID"><InlineValue value={event.span_id} /></Field>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
          <Field label="Event ID"><InlineValue value={event.id} /></Field>
          <Field label="Iteration">
            <span style={{ fontSize: 13, color: "var(--main-text)", fontFamily: "monospace" }}>
              {event.iteration_id != null ? String(event.iteration_id) : "—"}
            </span>
          </Field>
        </div>

        <div style={{ height: 1, background: "var(--card-border)" }} />

        {/* JSON fields */}
        <Field label="Input"><JsonBlock value={event.input} /></Field>
        <Field label="Output"><JsonBlock value={event.output} /></Field>
        <Field label="Metadata"><JsonBlock value={event.metadata} /></Field>
        {event.error != null && (
          <Field label="Error">
            <pre style={{
              margin: 0, fontSize: 12, lineHeight: 1.6,
              color: "#EF4444",
              background: "#EF444411",
              border: "1px solid #EF444433",
              borderRadius: 8, padding: "0.75rem 1rem",
              overflowX: "auto", whiteSpace: "pre-wrap", wordBreak: "break-all",
              maxHeight: 200, overflowY: "auto",
            }}>
              {JSON.stringify(event.error, null, 2)}
            </pre>
          </Field>
        )}
      </div>
    </div>
  )
}
