"use client"

import { useState, useTransition, useRef, useEffect } from "react"
import { removeUser } from "@/app/dashboard/directory/users/actions"

export default function UserActionsMenu({
  userId,
  isOwner,
}: {
  userId: string
  isOwner: boolean
}) {
  const [open, setOpen]              = useState(false)
  const [isPending, startTransition] = useTransition()
  const [error, setError]            = useState<string | null>(null)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [])

  function handleDelete() {
    setOpen(false)
    startTransition(async () => {
      const res = await removeUser(userId)
      if (res.error) setError(res.error)
    })
  }

  if (!isOwner) return null

  return (
    <div ref={ref} style={{ position: "relative", display: "inline-block" }}>
      <button
        onClick={() => setOpen(o => !o)}
        disabled={isPending}
        style={{
          background: "none", border: "none",
          cursor: "pointer", color: "var(--text-muted)",
          fontSize: 18, lineHeight: 1, padding: "0.25rem 0.5rem",
          borderRadius: 6,
        }}
      >
        {isPending ? "…" : "⋯"}
      </button>

      {error && (
        <div style={{ position: "absolute", right: 0, top: "110%", fontSize: 12, color: "#EF4444", whiteSpace: "nowrap", background: "var(--card-bg)", border: "1px solid var(--card-border)", borderRadius: 6, padding: "0.35rem 0.65rem", zIndex: 10 }}>
          {error}
        </div>
      )}

      {open && (
        <div style={{
          position: "absolute", right: 0, top: "110%",
          background: "var(--card-bg)",
          border: "1px solid var(--card-border)",
          borderRadius: 8, padding: "0.25rem",
          minWidth: 140, zIndex: 10,
          boxShadow: "0 4px 16px rgba(0,0,0,0.15)",
        }}>
          <button
            onClick={handleDelete}
            style={{
              display: "block", width: "100%", textAlign: "left",
              padding: "0.5rem 0.75rem", borderRadius: 6,
              background: "none", border: "none",
              fontSize: 13, color: "#EF4444",
              cursor: "pointer",
            }}
          >
            Remove user
          </button>
        </div>
      )}
    </div>
  )
}
