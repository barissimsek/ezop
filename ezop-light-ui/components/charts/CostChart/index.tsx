"use client"

import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts"

type DataPoint = {
  time: string
  llmCost: number
}

const fmt = (v: number) => `$${Number(v).toFixed(5)}`

export default function CostChart({ data }: { data: DataPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <AreaChart data={data} margin={{ top: 4, right: 16, left: -4, bottom: 0 }}>
        <defs>
          <linearGradient id="gLlm" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="var(--accent)" stopOpacity={0.3} />
            <stop offset="95%" stopColor="var(--accent)" stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
        <XAxis dataKey="time" tick={{ fontSize: 12, fill: "var(--text-muted)" }} />
        <YAxis tickFormatter={fmt} tick={{ fontSize: 12, fill: "var(--text-muted)" }} />
        <Tooltip
          contentStyle={{ background: "var(--card-bg)", border: "1px solid var(--card-border)", borderRadius: 8 }}
          labelStyle={{ color: "var(--main-text)" }}
          formatter={(v) => [fmt(Number(v)), ""]}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Area type="monotone" dataKey="llmCost" stroke="var(--accent)" fill="url(#gLlm)" strokeWidth={2} name="LLM Cost" />
      </AreaChart>
    </ResponsiveContainer>
  )
}
