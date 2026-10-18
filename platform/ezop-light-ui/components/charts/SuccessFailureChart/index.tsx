"use client";

import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

type StatusCounts = {
  running: number
  success: number
  failed: number
  partial: number
  canceled: number
}

const SLICES = [
  { key: "running",  name: "Running",  color: "var(--accent)" },
  { key: "success",  name: "Success",  color: "#10B981" },
  { key: "failed",   name: "Failed",   color: "#EF4444" },
  { key: "partial",  name: "Partial",  color: "#F59E0B" },
  { key: "canceled", name: "Cancelled",color: "#6B7280" },
] as const

export default function SuccessFailureChart({ counts }: { counts: StatusCounts }) {
  const data = SLICES.map(s => ({ ...s, value: counts[s.key] })).filter(d => d.value > 0)
  const total = data.reduce((sum, d) => sum + d.value, 0);

  return (
    <div style={{ display: "flex", alignItems: "center", gap: "1.5rem" }}>
      <ResponsiveContainer width={200} height={200}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={55}
            outerRadius={85}
            paddingAngle={3}
            dataKey="value"
          >
            {data.map((entry) => (
              <Cell key={entry.name} fill={entry.color} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{
              background: "var(--card-bg)",
              border: "1px solid var(--card-border)",
              borderRadius: 8,
            }}
            labelStyle={{
              color: "var(--main-text)",
              fontFamily: "monospace",
              fontWeight: 600,
            }}
            formatter={(value) => {
              if (typeof value !== "number") return "N/A"
              const pct = total > 0 ? ((value / total) * 100).toFixed(1) : "0.0"
              return `${value} runs (${pct}%)`
            }}
            cursor={{ fill: "rgba(255,255,255,0.04)" }}
          />
        </PieChart>
      </ResponsiveContainer>

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "0.6rem",
          flex: 1,
        }}
      >
        {data.map((entry) => (
          <div
            key={entry.name}
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              fontSize: "0.85rem",
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
                color: "var(--main-text)",
              }}
            >
              <span
                style={{
                  width: 10,
                  height: 10,
                  borderRadius: "50%",
                  background: entry.color,
                  display: "inline-block",
                }}
              />
              {entry.name}
            </div>
            <span
              style={{
                color: "var(--text-muted)",
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {((entry.value / total) * 100).toFixed(1)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
