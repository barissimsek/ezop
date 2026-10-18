"use client"

import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell, ResponsiveContainer,
} from "recharts"

const data = [
  { tool: "web_search",       calls: 3200, color: "#2563EB" },
  { tool: "db_query",         calls: 900,  color: "#06B6D4" },
  { tool: "send_email",       calls: 480,  color: "#8B5CF6" },
  { tool: "code_interpreter", calls: 150,  color: "#F59E0B" },
  { tool: "file_reader",      calls: 98,   color: "#10B981" },
  { tool: "image_analyzer",   calls: 37,   color: "#6B7280" },
]

export default function ToolUsageChart() {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 48, left: 12, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" horizontal={false} />
        <XAxis type="number" tick={{ fontSize: 12, fill: "var(--text-muted)" }} />
        <YAxis
          type="category"
          dataKey="tool"
          tick={{ fontSize: 12, fill: "var(--text-muted)", fontFamily: "monospace" }}
          width={118}
        />
        <Tooltip
          contentStyle={{ background: "var(--card-bg)", border: "1px solid var(--card-border)", borderRadius: 8 }}
          labelStyle={{ color: "var(--main-text)", fontFamily: "monospace" }}
          formatter={(v) => [`${Number(v).toLocaleString()} calls`, ""]}
          cursor={{ fill: "rgba(255,255,255,0.04)" }}
        />
        <Bar dataKey="calls" radius={[0, 4, 4, 0]} maxBarSize={28}>
          {data.map((entry) => (
            <Cell key={entry.tool} fill={entry.color} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
