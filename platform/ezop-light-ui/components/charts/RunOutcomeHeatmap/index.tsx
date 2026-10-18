"use client"

import { useState } from "react"

const AGENTS = ["email-bot", "data-sync", "report-gen", "web-scraper", "alert-agent"]

const HOURS = Array.from({ length: 24 }, (_, i) =>
  i === 0 ? "12a" : i < 12 ? `${i}a` : i === 12 ? "12p" : `${i - 12}p`
)

// Dummy data: success rates per agent per hour (0–1)
// email-bot fails at night, data-sync fails at peak hours
const RAW: Record<string, number[]> = {
  "email-bot":   [0.1, 0.1, 0.1, 0.1, 0.1, 0.2, 0.8, 0.95, 0.97, 0.96, 0.95, 0.94, 0.93, 0.92, 0.94, 0.93, 0.92, 0.91, 0.7, 0.4, 0.2, 0.1, 0.1, 0.1],
  "data-sync":   [0.95, 0.96, 0.97, 0.96, 0.95, 0.94, 0.93, 0.92, 0.88, 0.6, 0.5, 0.94, 0.93, 0.92, 0.55, 0.5, 0.92, 0.93, 0.94, 0.95, 0.96, 0.97, 0.96, 0.95],
  "report-gen":  [0.9, 0.91, 0.9, 0.89, 0.9, 0.91, 0.92, 0.93, 0.94, 0.95, 0.94, 0.93, 0.92, 0.91, 0.92, 0.93, 0.94, 0.93, 0.92, 0.91, 0.9, 0.89, 0.9, 0.91],
  "web-scraper": [0.7, 0.72, 0.68, 0.71, 0.7, 0.75, 0.8, 0.82, 0.85, 0.83, 0.84, 0.82, 0.81, 0.83, 0.82, 0.81, 0.8, 0.79, 0.78, 0.75, 0.73, 0.71, 0.7, 0.69],
  "alert-agent": [0.99, 0.99, 0.98, 0.99, 0.99, 0.99, 0.98, 0.97, 0.96, 0.95, 0.96, 0.97, 0.98, 0.99, 0.98, 0.97, 0.96, 0.97, 0.98, 0.99, 0.99, 0.99, 0.98, 0.99],
}

function rateToColor(rate: number): string {
  if (rate >= 0.9)  return "#10B981"
  if (rate >= 0.75) return "#84CC16"
  if (rate >= 0.5)  return "#F59E0B"
  if (rate >= 0.25) return "#EF4444"
  return "#7f1d1d"
}

export default function RunOutcomeHeatmap() {
  const [tooltip, setTooltip] = useState<{ agent: string; hour: string; rate: number } | null>(null)

  return (
    <div style={{ overflowX: "auto" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: "3px", minWidth: 520 }}>
        {/* Hour labels */}
        <div style={{ display: "flex", marginLeft: 90 }}>
          {HOURS.map((h, i) => (
            <div key={i} style={{
              flex: 1,
              fontSize: 9,
              color: "var(--text-muted)",
              textAlign: "center",
              fontFamily: "monospace",
            }}>
              {i % 3 === 0 ? h : ""}
            </div>
          ))}
        </div>

        {/* Rows */}
        {AGENTS.map((agent) => (
          <div key={agent} style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <div style={{
              width: 86,
              fontSize: 11,
              color: "var(--text-muted)",
              fontFamily: "monospace",
              textAlign: "right",
              flexShrink: 0,
              paddingRight: 4,
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}>
              {agent}
            </div>
            {RAW[agent].map((rate, i) => (
              <div
                key={i}
                onMouseEnter={() => setTooltip({ agent, hour: HOURS[i], rate })}
                onMouseLeave={() => setTooltip(null)}
                style={{
                  flex: 1,
                  height: 24,
                  borderRadius: 3,
                  background: rateToColor(rate),
                  opacity: 0.85,
                  cursor: "default",
                  transition: "opacity 0.1s",
                  position: "relative",
                }}
              />
            ))}
          </div>
        ))}

        {/* Legend */}
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginLeft: 90, marginTop: 8 }}>
          <span style={{ fontSize: 10, color: "var(--text-muted)" }}>0%</span>
          {["#7f1d1d", "#EF4444", "#F59E0B", "#84CC16", "#10B981"].map((c) => (
            <div key={c} style={{ width: 20, height: 10, borderRadius: 2, background: c }} />
          ))}
          <span style={{ fontSize: 10, color: "var(--text-muted)" }}>100%</span>
        </div>

        {/* Tooltip */}
        {tooltip && (
          <div style={{
            marginLeft: 90,
            marginTop: 4,
            fontSize: 12,
            color: "var(--main-text)",
            background: "var(--card-bg)",
            border: "1px solid var(--card-border)",
            borderRadius: 6,
            padding: "4px 10px",
            display: "inline-block",
          }}>
            <span style={{ fontFamily: "monospace" }}>{tooltip.agent}</span>
            {" · "}{tooltip.hour}
            {" · "}<strong>{(tooltip.rate * 100).toFixed(0)}% success</strong>
          </div>
        )}
      </div>
    </div>
  )
}
