"use client"

import { useState, useMemo } from "react"

// ─── Types ────────────────────────────────────────────────────────────────────

type Resource = "agent" | "apikey" | "run" | "user" | string

export type AuditEntry = {
  id: string
  ts: string               // ISO
  user: string
  userEmail: string
  event: string
  resource: Resource
  target: string
  description: string
  meta?: Record<string, unknown>
  diff?: { field: string; before: unknown; after: unknown }[]
}

// keep internal alias
type AuditEvent = AuditEntry

// ─── Dummy data ───────────────────────────────────────────────────────────────

// ─── Helpers ──────────────────────────────────────────────────────────────────

const RESOURCE_COLOR: Record<Resource, string> = {
  agent:  "#2563EB",
  apikey: "#8B5CF6",
  run:    "#06B6D4",
  user:   "#F59E0B",
}

const EVENT_LABELS: Record<string, string> = {
  "agent.created":          "Agent Created",
  "agent.updated":          "Agent Updated",
  "agent.deleted":          "Agent Deleted",
  "agent.version.published":"Version Published",
  "apikey.created":         "Key Created",
  "apikey.deleted":         "Key Deleted",
  "apikey.rotated":         "Key Rotated",
  "run.triggered":          "Run Triggered",
  "run.cancelled":          "Run Cancelled",
  "user.invited":           "User Invited",
  "user.removed":           "User Removed",
  "role.changed":           "Role Changed",
}

function fmtTs(iso: string) {
  const d = new Date(iso)
  return d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false })
}

function initials(name: string) {
  return name.split(" ").map(w => w[0]).join("").slice(0, 2).toUpperCase()
}

function Avatar({ name }: { name: string }) {
  const colors = ["#2563EB", "#8B5CF6", "#06B6D4", "#F59E0B", "#10B981"]
  const color = colors[name.charCodeAt(0) % colors.length]
  return (
    <div style={{
      width: 28, height: 28, borderRadius: "50%",
      background: color + "33", border: `1.5px solid ${color}`,
      display: "flex", alignItems: "center", justifyContent: "center",
      fontSize: 11, fontWeight: 700, color, flexShrink: 0,
    }}>
      {initials(name)}
    </div>
  )
}

function Badge({ event }: { event: string }) {
  const resource = event.split(".")[0] as Resource
  const color = RESOURCE_COLOR[resource] ?? "#6B7280"
  return (
    <span style={{
      display: "inline-block",
      padding: "2px 8px",
      borderRadius: 99,
      fontSize: 11,
      fontWeight: 500,
      background: color + "22",
      color,
      fontFamily: "monospace",
      whiteSpace: "nowrap",
    }}>
      {event}
    </span>
  )
}

function Diff({ diff }: { diff: AuditEvent["diff"] }) {
  if (!diff?.length) return null
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 4 }}>
      {diff.map((d) => (
        <div key={d.field} style={{ fontSize: 12 }}>
          <div style={{ fontFamily: "monospace", color: "var(--text-muted)", marginBottom: 4 }}>{d.field}</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
            <div style={{ background: "#EF444418", border: "1px solid #EF444430", borderRadius: 4, padding: "3px 8px", fontFamily: "monospace", color: "#EF4444", wordBreak: "break-all" }}>
              − {JSON.stringify(d.before)}
            </div>
            <div style={{ background: "#10B98118", border: "1px solid #10B98130", borderRadius: 4, padding: "3px 8px", fontFamily: "monospace", color: "#10B981", wordBreak: "break-all" }}>
              + {JSON.stringify(d.after)}
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

function Meta({ meta }: { meta: AuditEvent["meta"] }) {
  if (!meta) return null
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 4 }}>
      {Object.entries(meta).map(([k, v]) => (
        <div key={k} style={{ display: "flex", gap: 8, fontSize: 12 }}>
          <span style={{ fontFamily: "monospace", color: "var(--text-muted)", flexShrink: 0 }}>{k}</span>
          <span style={{ color: "var(--main-text)", fontFamily: "monospace", wordBreak: "break-all" }}>{JSON.stringify(v)}</span>
        </div>
      ))}
    </div>
  )
}

// ─── Detail Panel ─────────────────────────────────────────────────────────────

function DetailPanel({ entry, onClose }: { entry: AuditEvent; onClose: () => void }) {
  const resource = entry.event.split(".")[0] as Resource
  const color = RESOURCE_COLOR[resource] ?? "#6B7280"

  return (
    <div style={{
      width: 360,
      flexShrink: 0,
      background: "var(--card-bg)",
      border: "1px solid var(--card-border)",
      borderRadius: 12,
      padding: "1.25rem",
      display: "flex",
      flexDirection: "column",
      gap: "1rem",
      alignSelf: "flex-start",
      position: "sticky",
      top: 0,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <Badge event={entry.event} />
        <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", fontSize: 18, lineHeight: 1, padding: 0 }}>×</button>
      </div>

      <div>
        <div style={{ fontWeight: 600, fontSize: "0.95rem", color: "var(--main-text)" }}>{entry.description}</div>
        <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>{new Date(entry.ts).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" })}</div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <Row label="User"     value={`${entry.user} · ${entry.userEmail}`} />
        <Row label="Resource" value={entry.target} color={color} mono />
        <Row label="Event ID" value={entry.id} mono muted />
      </div>

      {entry.diff && (
        <Section title="Changes">
          <Diff diff={entry.diff} />
        </Section>
      )}

      {entry.meta && (
        <Section title="Metadata">
          <Meta meta={entry.meta} />
        </Section>
      )}

      <div style={{ fontSize: 10, color: "var(--text-muted)", paddingTop: 4, borderTop: "1px solid var(--card-border)" }}>
        This record is immutable and append-only.
      </div>
    </div>
  )
}

function Row({ label, value, color, mono, muted }: { label: string; value: string; color?: string; mono?: boolean; muted?: boolean }) {
  return (
    <div style={{ display: "flex", gap: 8, fontSize: 12 }}>
      <span style={{ color: "var(--text-muted)", minWidth: 64, flexShrink: 0 }}>{label}</span>
      <span style={{ color: color ?? (muted ? "var(--text-muted)" : "var(--main-text)"), fontFamily: mono ? "monospace" : undefined, wordBreak: "break-all" }}>{value}</span>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-muted)" }}>{title}</div>
      {children}
    </div>
  )
}

// ─── Filters ──────────────────────────────────────────────────────────────────

const ALL_RESOURCES = ["all", "agent", "apikey", "run", "user"] as const
const ALL_EVENTS    = ["all", ...Object.keys(EVENT_LABELS)] as const
const TIME_RANGES   = ["all", "today", "7d", "30d"] as const

type Filters = {
  resource: string
  event: string
  user: string
  range: string
}

function inRange(iso: string, range: string): boolean {
  const now = Date.now()
  const t = new Date(iso).getTime()
  if (range === "today") return now - t < 86400000
  if (range === "7d")    return now - t < 7 * 86400000
  if (range === "30d")   return now - t < 30 * 86400000
  return true
}

function Select({ label, value, options, onChange }: {
  label: string; value: string; options: readonly string[]; onChange: (v: string) => void
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <label style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</label>
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        style={{
          padding: "0.4rem 0.6rem",
          borderRadius: 6,
          border: "1px solid var(--card-border)",
          background: "var(--card-bg)",
          color: "var(--main-text)",
          fontSize: 13,
          cursor: "pointer",
        }}
      >
        {options.map(o => <option key={o} value={o}>{o === "all" ? `All ${label}s` : (EVENT_LABELS[o] ?? o)}</option>)}
      </select>
    </div>
  )
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function AuditLog({ logs = [] }: { logs?: AuditEntry[] }) {
  const [selected, setSelected] = useState<AuditEvent | null>(null)
  const [filters, setFilters] = useState<Filters>({ resource: "all", event: "all", user: "all", range: "all" })

  const patch = (k: keyof Filters) => (v: string) => setFilters(f => ({ ...f, [k]: v }))

  const allUsers = useMemo(() =>
    ["all", ...Array.from(new Set(logs.map(e => e.user))).sort()],
    [logs]
  )

  const filtered = useMemo(() => logs.filter(e =>
    (filters.resource === "all" || e.resource === filters.resource) &&
    (filters.event    === "all" || e.event    === filters.event)    &&
    (filters.user     === "all" || e.user     === filters.user)     &&
    inRange(e.ts, filters.range)
  ), [filters])

  return (
    <div style={{ display: "flex", gap: "1.5rem", alignItems: "flex-start" }}>
      {/* Main column */}
      <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: "1rem" }}>

        {/* Filters */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
          gap: "0.75rem",
          background: "var(--card-bg)",
          border: "1px solid var(--card-border)",
          borderRadius: 12,
          padding: "1rem 1.25rem",
        }}>
          <Select label="Resource"   value={filters.resource} options={ALL_RESOURCES} onChange={patch("resource")} />
          <Select label="Event"      value={filters.event}    options={ALL_EVENTS}    onChange={patch("event")} />
          <Select label="User"       value={filters.user}     options={allUsers}     onChange={patch("user")} />
          <Select label="Time range" value={filters.range}    options={TIME_RANGES}   onChange={patch("range")} />
        </div>

        {/* Table */}
        <div style={{ background: "var(--card-bg)", border: "1px solid var(--card-border)", borderRadius: 12, overflow: "hidden" }}>
          {/* Header */}
          <div style={{ display: "grid", gridTemplateColumns: "140px 1fr 160px 120px", gap: "0.5rem", padding: "0.65rem 1.25rem", borderBottom: "1px solid var(--card-border)" }}>
            {["Timestamp", "Event · Target", "User", ""].map(h => (
              <div key={h} style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-muted)" }}>{h}</div>
            ))}
          </div>

          {filtered.length === 0 && (
            <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-muted)", fontSize: 14 }}>
              No events match the current filters.
            </div>
          )}

          {filtered.map((entry) => {
            const isSelected = selected?.id === entry.id
            return (
              <div
                key={entry.id}
                onClick={() => setSelected(isSelected ? null : entry)}
                style={{
                  display: "grid",
                  gridTemplateColumns: "140px 1fr 160px 120px",
                  gap: "0.5rem",
                  padding: "0.85rem 1.25rem",
                  borderBottom: "1px solid var(--card-border)",
                  cursor: "pointer",
                  background: isSelected ? "var(--sidebar-active-bg)" : "transparent",
                  transition: "background 0.1s",
                  alignItems: "center",
                }}
              >
                {/* Timestamp */}
                <div style={{ fontSize: 12, color: "var(--text-muted)", fontVariantNumeric: "tabular-nums", fontFamily: "monospace" }}>
                  {fmtTs(entry.ts)}
                </div>

                {/* Event + target */}
                <div style={{ display: "flex", flexDirection: "column", gap: 3, minWidth: 0 }}>
                  <Badge event={entry.event} />
                  <div style={{ fontSize: 12, color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {entry.target}
                  </div>
                </div>

                {/* User */}
                <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
                  <Avatar name={entry.user} />
                  <span style={{ fontSize: 13, color: "var(--main-text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{entry.user}</span>
                </div>

                {/* Detail indicator */}
                <div style={{ fontSize: 12, color: "var(--text-muted)", textAlign: "right" }}>
                  {(entry.diff || entry.meta) && (
                    <span style={{ opacity: 0.6 }}>{isSelected ? "▼ open" : "▶ details"}</span>
                  )}
                </div>
              </div>
            )
          })}
        </div>

        <div style={{ fontSize: 12, color: "var(--text-muted)", textAlign: "right" }}>
          {filtered.length} event{filtered.length !== 1 ? "s" : ""}
          {" · "}
          <span style={{ fontFamily: "monospace" }}>append-only · immutable</span>
        </div>
      </div>

      {/* Detail panel */}
      {selected && <DetailPanel entry={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}
