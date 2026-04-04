"use client"

import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer,
} from "recharts"

const COLORS = ["#FCA5A5", "#DC2626", "#7F1D1D"]

const fmt = (v: number) => `${v}%`

type Props = {
  data: Record<string, string | number>[]
  versions: string[]
}

export default function PromptVersionChart({ data = [], versions = [] }: Props) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} margin={{ top: 16, right: 16, left: -8, bottom: 0 }} barCategoryGap="28%">
        <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" vertical={false} />
        <XAxis dataKey="agent" tick={{ fontSize: 12, fill: "var(--text-muted)" }} />
        <YAxis
          domain={[0, 100]}
          tickFormatter={fmt}
          tick={{ fontSize: 12, fill: "var(--text-muted)" }}
        />
        <Tooltip
          contentStyle={{ background: "var(--card-bg)", border: "1px solid var(--card-border)", borderRadius: 8 }}
          labelStyle={{ color: "var(--main-text)", fontWeight: 600 }}
          formatter={(v, name) => [`${Number(v)}%`, String(name)]}
          cursor={{ fill: "rgba(255,255,255,0.04)" }}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        {versions.map((v, i) => (
          <Bar
            key={v}
            dataKey={v}
            name={v}
            fill={COLORS[i % COLORS.length]}
            fillOpacity={0.15}
            stroke={COLORS[i % COLORS.length]}
            strokeWidth={1.5}
            radius={[4, 4, 0, 0]}
            maxBarSize={32}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  )
}
