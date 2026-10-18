"use client"

import { useState } from "react"
import EventDetailModal, { type EventDetail } from "@/components/EventDetailModal"

function fmt(ts: string) {
  return new Date(ts).toLocaleString(undefined, {
    month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  })
}

export default function EventsTable({
  events,
  runToAgent,
}: {
  events: EventDetail[]
  runToAgent: Record<string, string>
}) {
  const [selected, setSelected] = useState<EventDetail | null>(null)

  return (
    <>
      <div style={{
        background: "var(--card-bg)", border: "1px solid var(--card-border)",
        borderRadius: 12, overflow: "hidden",
      }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: "1px solid var(--card-border)" }}>
              {["Timestamp", "Agent", "Name", "Category", "Type"].map(h => (
                <th key={h} style={{
                  padding: "0.75rem 1rem", textAlign: "left",
                  fontSize: 11, fontWeight: 600, letterSpacing: "0.06em",
                  textTransform: "uppercase", color: "var(--text-muted)",
                }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {events.length === 0 ? (
              <tr>
                <td colSpan={5} style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)" }}>
                  No events found
                </td>
              </tr>
            ) : events.map((e, i) => (
              <tr
                key={e.id}
                onClick={() => setSelected(e)}
                style={{
                  borderBottom: i < events.length - 1 ? "1px solid var(--card-border)" : "none",
                  cursor: "pointer",
                  transition: "background 0.1s",
                }}
                onMouseEnter={ev => (ev.currentTarget.style.background = "var(--sidebar-active-bg)")}
                onMouseLeave={ev => (ev.currentTarget.style.background = "")}
              >
                <td style={{ padding: "0.7rem 1rem", color: "var(--text-muted)", whiteSpace: "nowrap", fontVariantNumeric: "tabular-nums" }}>
                  {fmt(e.timestamp)}
                </td>
                <td style={{ padding: "0.7rem 1rem", color: "var(--main-text)" }}>
                  {runToAgent[e.run_id] ?? "—"}
                </td>
                <td style={{ padding: "0.7rem 1rem", color: "var(--main-text)", fontFamily: "monospace" }}>
                  {e.name}
                </td>
                <td style={{ padding: "0.7rem 1rem" }}>
                  {e.category ? (
                    <span style={{
                      padding: "0.2rem 0.55rem", borderRadius: 6,
                      background: "var(--sidebar-active-bg)",
                      color: "var(--accent)", fontSize: 12, fontWeight: 500,
                    }}>
                      {e.category}
                    </span>
                  ) : "—"}
                </td>
                <td style={{ padding: "0.7rem 1rem", color: "var(--text-muted)", fontSize: 12 }}>
                  {e.type ?? "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selected && (
        <EventDetailModal event={selected} onClose={() => setSelected(null)} />
      )}
    </>
  )
}
