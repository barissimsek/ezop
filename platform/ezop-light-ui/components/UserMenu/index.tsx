"use client"

import { useState, useRef, useEffect } from "react"

export default function UserMenu({
  name,
  onSignOut,
}: {
  name: string | null | undefined
  onSignOut: () => void
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener("mousedown", handleClick)
    return () => document.removeEventListener("mousedown", handleClick)
  }, [])

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          width: "100%",
          padding: "0.45rem 0.75rem",
          background: open ? "var(--sidebar-active-bg)" : "transparent",
          border: "1px solid transparent",
          borderRadius: "6px",
          color: "var(--sidebar-text-muted)",
          cursor: "pointer",
          textAlign: "left",
          fontSize: "0.8rem",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "0.5rem",
        }}
      >
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {name ?? "Account"}
        </span>
        <span style={{ fontSize: 10, opacity: 0.6, flexShrink: 0 }}>▲</span>
      </button>

      {open && (
        <div style={{
          position: "absolute",
          bottom: "calc(100% + 6px)",
          left: 0,
          right: 0,
          background: "var(--card-bg)",
          border: "1px solid var(--card-border)",
          borderRadius: 8,
          overflow: "hidden",
          boxShadow: "0 4px 16px rgba(0,0,0,0.2)",
          zIndex: 100,
        }}>
          <a
            href="https://www.ezop.ai/docs"
            target="_blank"
            rel="noopener noreferrer"
            onClick={() => setOpen(false)}
            style={{
              display: "block",
              padding: "0.6rem 0.85rem",
              fontSize: 13,
              color: "var(--main-text)",
              textDecoration: "none",
              borderBottom: "1px solid var(--card-border)",
            }}
            onMouseEnter={e => (e.currentTarget.style.background = "var(--sidebar-active-bg)")}
            onMouseLeave={e => (e.currentTarget.style.background = "")}
          >
            Documentation
          </a>
          <a
            href="https://www.ezop.ai/support"
            target="_blank"
            rel="noopener noreferrer"
            onClick={() => setOpen(false)}
            style={{
              display: "block",
              padding: "0.6rem 0.85rem",
              fontSize: 13,
              color: "var(--main-text)",
              textDecoration: "none",
              borderBottom: "1px solid var(--card-border)",
            }}
            onMouseEnter={e => (e.currentTarget.style.background = "var(--sidebar-active-bg)")}
            onMouseLeave={e => (e.currentTarget.style.background = "")}
          >
            Support
          </a>
          <button
            onClick={() => { setOpen(false); onSignOut() }}
            style={{
              display: "block",
              width: "100%",
              padding: "0.6rem 0.85rem",
              fontSize: 13,
              color: "#EF4444",
              background: "none",
              border: "none",
              cursor: "pointer",
              textAlign: "left",
            }}
            onMouseEnter={e => (e.currentTarget.style.background = "var(--sidebar-active-bg)")}
            onMouseLeave={e => (e.currentTarget.style.background = "")}
          >
            Logout
          </button>
        </div>
      )}
    </div>
  )
}
