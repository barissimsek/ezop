"use client"

import { useRouter } from "next/navigation"

type Agent = { id: string; name: string }

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

export default function PerformanceFilters({
  agents,
  timeRange,
  agentId,
}: {
  agents: Agent[]
  timeRange: string
  agentId: string
}) {
  const router = useRouter()

  function update(key: string, value: string) {
    const params = new URLSearchParams(window.location.search)
    params.set(key, value)
    router.push(`?${params.toString()}`)
  }

  return (
    <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
      <select style={selectStyle} value={timeRange} onChange={e => update("timeRange", e.target.value)}>
        <option value="1">Last day</option>
        <option value="3">Last 3 days</option>
        <option value="7">Last 7 days</option>
        <option value="14">Last 14 days</option>
        <option value="30">Last 30 days</option>
        <option value="90">Last 90 days</option>
      </select>

      <select style={selectStyle} value={agentId} onChange={e => update("agentId", e.target.value)}>
        <option value="">All Agents</option>
        {agents.map(a => (
          <option key={a.id} value={a.id}>{a.name}</option>
        ))}
      </select>
    </div>
  )
}
