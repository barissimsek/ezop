"use client"

import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell, ResponsiveContainer,
} from "recharts"

const data = [
  { type: "parsing_failure", count: 214, color: "#EF4444" },
  { type: "tool_error",      count: 138, color: "#F59E0B" },
  { type: "rate_limit",      count: 97,  color: "#8B5CF6" },
  { type: "model_timeout",   count: 61,  color: "#06B6D4" },
  { type: "invalid_output",  count: 42,  color: "#6B7280" },
]

const total = data.reduce((sum, d) => sum + d.count, 0)

export default function ErrorDistributionChart() {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 48, left: 8, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" horizontal={false} />
        <XAxis type="number" tick={{ fontSize: 12, fill: "var(--text-muted)" }} />
        <YAxis
          type="category"
          dataKey="type"
          tick={{ fontSize: 12, fill: "var(--text-muted)", fontFamily: "monospace" }}
          width={110}
        />
        <Tooltip
          contentStyle={{ background: "var(--card-bg)", border: "1px solid var(--card-border)", borderRadius: 8 }}
          labelStyle={{ color: "var(--main-text)", fontFamily: "monospace" }}
          formatter={(v) => { const n = Number(v); return [`${n} (${((n / total) * 100).toFixed(1)}%)`, "occurrences"] }}
          cursor={{ fill: "rgba(255,255,255,0.04)" }}
        />
        <Bar dataKey="count" radius={[0, 4, 4, 0]} maxBarSize={28}>
          {data.map((entry) => (
            <Cell key={entry.type} fill={entry.color} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
