"use client"

import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts"

type DataPoint = {
  time: string
  running: number
  success: number
  failed: number
  partial: number
  canceled: number
}

export default function AgentActivityChart({ data }: { data: DataPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={data} margin={{ top: 4, right: 16, left: -16, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
        <XAxis dataKey="time" tick={{ fontSize: 12, fill: "var(--text-muted)" }} />
        <YAxis tick={{ fontSize: 12, fill: "var(--text-muted)" }} />
        <Tooltip
          contentStyle={{ background: "var(--card-bg)", border: "1px solid var(--card-border)", borderRadius: 8 }}
          labelStyle={{ color: "var(--main-text)" }}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Line type="monotone" dataKey="running"  stroke="var(--accent)" strokeWidth={2} dot={false} name="Running" />
        <Line type="monotone" dataKey="success"  stroke="#10B981"       strokeWidth={2} dot={false} name="Success" />
        <Line type="monotone" dataKey="failed"   stroke="#EF4444"       strokeWidth={2} dot={false} name="Failed" />
        <Line type="monotone" dataKey="partial"  stroke="#F59E0B"       strokeWidth={2} dot={false} name="Partial" />
        <Line type="monotone" dataKey="canceled" stroke="#6B7280"       strokeWidth={2} dot={false} name="Canceled" />
      </LineChart>
    </ResponsiveContainer>
  )
}
