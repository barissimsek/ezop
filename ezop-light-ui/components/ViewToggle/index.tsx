"use client"

import { useRouter } from "next/navigation"

type View = "flat" | "tree"

const FlatIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
    <rect x="1" y="3" width="14" height="2" rx="1" fill="currentColor" />
    <rect x="1" y="7" width="14" height="2" rx="1" fill="currentColor" />
    <rect x="1" y="11" width="14" height="2" rx="1" fill="currentColor" />
  </svg>
)

const TreeIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
    {/* root node */}
    <rect x="5.5" y="1" width="5" height="3.5" rx="1" fill="currentColor" />
    {/* vertical stem down from root */}
    <line x1="8" y1="4.5" x2="8" y2="7" stroke="currentColor" strokeWidth="1.2" />
    {/* horizontal branch */}
    <line x1="3.5" y1="7" x2="12.5" y2="7" stroke="currentColor" strokeWidth="1.2" />
    {/* left stem down */}
    <line x1="3.5" y1="7" x2="3.5" y2="9" stroke="currentColor" strokeWidth="1.2" />
    {/* right stem down */}
    <line x1="12.5" y1="7" x2="12.5" y2="9" stroke="currentColor" strokeWidth="1.2" />
    {/* left child node */}
    <rect x="1" y="9" width="5" height="3.5" rx="1" fill="currentColor" />
    {/* right child node */}
    <rect x="10" y="9" width="5" height="3.5" rx="1" fill="currentColor" />
  </svg>
)

export default function ViewToggle({ current }: { current: View }) {
  const router = useRouter()

  function setView(v: View) {
    const params = new URLSearchParams(window.location.search)
    params.set("view", v)
    router.push(`?${params.toString()}`)
  }

  const btnStyle = (active: boolean): React.CSSProperties => ({
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    width: 32,
    height: 32,
    borderRadius: 6,
    border: "1px solid var(--card-border)",
    background: active ? "var(--sidebar-active-bg)" : "var(--card-bg)",
    color: active ? "var(--accent)" : "var(--text-muted)",
    cursor: "pointer",
  })

  return (
    <div style={{ display: "flex", gap: "0.375rem" }}>
      <button style={btnStyle(current === "flat")} onClick={() => setView("flat")} title="Flat view">
        <FlatIcon />
      </button>
      <button style={btnStyle(current === "tree")} onClick={() => setView("tree")} title="Hierarchy view">
        <TreeIcon />
      </button>
    </div>
  )
}
