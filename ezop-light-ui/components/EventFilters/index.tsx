"use client"

import { useRouter } from "next/navigation"

type Agent = { id: string; name: string }

export const TIME_OPTIONS = [
  { value: "5m",  label: "Last 5 min" },
  { value: "1h",  label: "Last hour" },
  { value: "3h",  label: "Last 3 hours" },
  { value: "6h",  label: "Last 6 hours" },
  { value: "12h", label: "Last 12 hours" },
  { value: "24h", label: "Last 24 hours" },
  { value: "2d",  label: "Last 2 days" },
  { value: "7d",  label: "Last 7 days" },
]

export const PAGE_SIZE_OPTIONS = [10, 25, 50]

const selectStyle: React.CSSProperties = {
  padding: "0.45rem 0.75rem",
  borderRadius: 8,
  border: "1px solid var(--card-border)",
  background: "var(--card-bg)",
  color: "var(--main-text)",
  fontSize: 13,
  cursor: "pointer",
  outline: "none",
}

type Props = {
  agents: Agent[]
  timeRange: string
  agentId: string
  pageSize: number
}

export default function EventFilters({ agents, timeRange, agentId, pageSize }: Props) {
  const router = useRouter()

  function update(key: string, value: string) {
    const params = new URLSearchParams(window.location.search)
    params.set(key, value)
    if (key !== "page") params.set("page", "1") // reset page on filter change
    router.push(`?${params.toString()}`)
  }

  return (
    <div style={{ display: "flex", gap: "0.75rem", alignItems: "center", flexWrap: "wrap" }}>
      <select style={selectStyle} value={timeRange} onChange={e => update("timeRange", e.target.value)}>
        {TIME_OPTIONS.map(o => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>

      <select style={selectStyle} value={agentId} onChange={e => update("agentId", e.target.value)}>
        <option value="">All Agents</option>
        {agents.map(a => (
          <option key={a.id} value={a.id}>{a.name}</option>
        ))}
      </select>

      <select style={selectStyle} value={pageSize} onChange={e => update("pageSize", e.target.value)}>
        {PAGE_SIZE_OPTIONS.map(s => (
          <option key={s} value={s}>{s} rows</option>
        ))}
      </select>
    </div>
  )
}
