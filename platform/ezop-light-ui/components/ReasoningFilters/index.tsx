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

export default function ReasoningFilters({
  agents,
  agentId,
}: {
  agents: Agent[]
  agentId: string
}) {
  const router = useRouter()

  function update(value: string) {
    const params = new URLSearchParams(window.location.search)
    params.set("agentId", value)
    router.push(`?${params.toString()}`)
  }

  return (
    <select style={selectStyle} value={agentId} onChange={e => update(e.target.value)}>
      {agents.map(a => (
        <option key={a.id} value={a.id}>{a.name}</option>
      ))}
    </select>
  )
}
