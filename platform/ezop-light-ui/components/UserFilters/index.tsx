"use client"

import { useRouter } from "next/navigation"
import { useRef } from "react"

const PAGE_SIZES = [10, 25, 50]

export default function UserFilters({
  search,
  pageSize,
}: {
  search: string
  pageSize: number
}) {
  const router = useRouter()
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  function update(patch: Record<string, string>) {
    const params = new URLSearchParams(window.location.search)
    for (const [k, v] of Object.entries(patch)) {
      if (v) params.set(k, v)
      else params.delete(k)
    }
    params.set("page", "1")
    router.push(`?${params.toString()}`)
  }

  function onSearch(e: React.ChangeEvent<HTMLInputElement>) {
    const val = e.target.value
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => update({ search: val }), 300)
  }

  const selectStyle: React.CSSProperties = {
    padding: "0.45rem 0.65rem",
    borderRadius: 8,
    border: "1px solid var(--card-border)",
    background: "var(--card-bg)",
    color: "var(--main-text)",
    fontSize: 13,
    cursor: "pointer",
  }

  return (
    <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
      <input
        type="search"
        defaultValue={search}
        onChange={onSearch}
        placeholder="Search by name or email…"
        style={{
          ...selectStyle,
          width: 260,
          outline: "none",
        }}
      />
      <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginLeft: "auto" }}>
        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Rows</span>
        <select
          value={pageSize}
          onChange={e => update({ pageSize: e.target.value })}
          style={selectStyle}
        >
          {PAGE_SIZES.map(n => (
            <option key={n} value={n}>{n}</option>
          ))}
        </select>
      </div>
    </div>
  )
}
