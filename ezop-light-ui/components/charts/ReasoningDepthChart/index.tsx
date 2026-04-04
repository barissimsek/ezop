"use client"

import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ReferenceArea, ReferenceLine, ResponsiveContainer,
} from "recharts"

const SWEET_MIN = 3
const SWEET_MAX = 8

const COLORS = ["#EF4444", "#F59E0B", "#10B981", "#2563EB", "#8B5CF6", "#06B6D4"]

type Props = {
  data: Record<string, string | number>[]
  agentNames: string[]
}

export default function ReasoningDepthChart({ data, agentNames }: Props) {
  if (data.length === 0 || agentNames.length === 0) {
    return (
      <div style={{ height: 280, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-muted)", fontSize: 13 }}>
        No completed runs in the last 30 days.
      </div>
    )
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap" }}>
        <Pill color="#10B981" label="Sweet spot" note={`${SWEET_MIN}–${SWEET_MAX} depth`} />
        <Pill color="#F59E0B" label="Too shallow" note={`< ${SWEET_MIN} — underthinkers`} />
        <Pill color="#EF4444" label="Too deep"   note={`> ${SWEET_MAX} — token burners`} />
      </div>

      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={data} margin={{ top: 8, right: 16, left: -8, bottom: 0 }}>
          {/* Too shallow zone */}
          <ReferenceArea y1={0} y2={SWEET_MIN} fill="#F59E0B" fillOpacity={0.06} stroke="none" />
          {/* Sweet spot zone */}
          <ReferenceArea y1={SWEET_MIN} y2={SWEET_MAX} fill="#10B981" fillOpacity={0.08} stroke="none" />
          {/* Too deep zone */}
          <ReferenceArea y1={SWEET_MAX} y2={9999} fill="#EF4444" fillOpacity={0.06} stroke="none" />
          <ReferenceLine y={SWEET_MIN} stroke="#F59E0B" strokeDasharray="4 3" strokeOpacity={0.6} strokeWidth={1} />
          <ReferenceLine y={SWEET_MAX} stroke="#EF4444" strokeDasharray="4 3" strokeOpacity={0.6} strokeWidth={1} />

          <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
          <XAxis dataKey="day" tick={{ fontSize: 12, fill: "var(--text-muted)" }} />
          <YAxis
            tick={{ fontSize: 12, fill: "var(--text-muted)" }}
            label={{ value: "depth", angle: -90, position: "insideLeft", offset: 12, fontSize: 11, fill: "var(--text-muted)" }}
            domain={[0, (dataMax: number) => Math.max(dataMax, SWEET_MAX + 2)]}
          />
          <Tooltip
            contentStyle={{ background: "var(--card-bg)", border: "1px solid var(--card-border)", borderRadius: 8 }}
            labelStyle={{ color: "var(--main-text)", fontWeight: 600 }}
            formatter={(v, name) => {
              const n = Number(v)
              const flag = n > SWEET_MAX ? " ⚠ too deep" : n < SWEET_MIN ? " ⚠ too shallow" : " ✓"
              return [`depth ${n}${flag}`, String(name)]
            }}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />

          {agentNames.map((name, i) => (
            <Line
              key={name}
              type="monotone"
              dataKey={name}
              stroke={COLORS[i % COLORS.length]}
              strokeWidth={2}
              dot={{ r: 3 }}
              activeDot={{ r: 5 }}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

function Pill({ color, label, note }: { color: string; label: string; note: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.78rem" }}>
      <span style={{ width: 10, height: 10, borderRadius: "50%", background: color, display: "inline-block", flexShrink: 0 }} />
      <span style={{ color: "var(--main-text)", fontWeight: 500 }}>{label}</span>
      <span style={{ color: "var(--text-muted)" }}>— {note}</span>
    </div>
  )
}
