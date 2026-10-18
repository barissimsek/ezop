"use client"

import { useState, useTransition, useMemo } from "react"
import { importUsers } from "@/app/dashboard/directory/users/actions"
import type { ImportResult } from "@/app/dashboard/directory/users/actions"

function parseEmails(text: string): string[] {
  return text
    .split(/[\n,;]+/)
    .map(e => e.trim().toLowerCase())
    .filter(e => e.includes("@"))
}

export default function ImportUsersModal({
  isOwner,
  availableSeats,
  userLimit,
}: {
  isOwner: boolean
  availableSeats: number
  userLimit: number
}) {
  const [open, setOpen]         = useState(false)
  const [text, setText]         = useState("")
  const [result, setResult]     = useState<ImportResult | null>(null)
  const [isPending, startTransition] = useTransition()

  const emails = useMemo(() => parseEmails(text), [text])
  const capped  = emails.slice(0, availableSeats)
  const overCount = Math.max(0, emails.length - availableSeats)

  function close() { setOpen(false); setText(""); setResult(null) }

  function submit() {
    if (!capped.length) return
    startTransition(async () => {
      const res = await importUsers(capped)
      setResult(res)
    })
  }

  return (
    <>
      <button
        disabled={!isOwner}
        onClick={() => setOpen(true)}
        title={!isOwner ? "Only the organization owner can import users" : undefined}
        style={{
          padding: "0.4rem 0.9rem",
          borderRadius: 8,
          border: "1px solid var(--card-border)",
          background: "transparent",
          color: isOwner ? "var(--main-text)" : "var(--text-muted)",
          fontSize: 13,
          fontWeight: 600,
          cursor: isOwner ? "pointer" : "not-allowed",
          opacity: isOwner ? 1 : 0.5,
        }}
      >
        Import Users
      </button>

      {open && (
        <div
          onClick={close}
          style={{
            position: "fixed", inset: 0,
            background: "rgba(0,0,0,0.5)",
            display: "flex", alignItems: "center", justifyContent: "center",
            zIndex: 1000,
          }}
        >
          <div
            onClick={e => e.stopPropagation()}
            style={{
              background: "var(--card-bg)",
              border: "1px solid var(--card-border)",
              borderRadius: 14,
              padding: "1.75rem",
              width: 500,
              display: "flex",
              flexDirection: "column",
              gap: "1.25rem",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <h2 style={{ margin: 0, fontSize: "1.1rem", fontWeight: 700, color: "var(--main-text)" }}>
                Import Users
              </h2>
              <button
                onClick={close}
                style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", fontSize: 20, lineHeight: 1 }}
              >×</button>
            </div>

            {/* Seat info */}
            <div style={{
              display: "flex", alignItems: "center", justifyContent: "space-between",
              padding: "0.65rem 1rem",
              background: availableSeats > 0 ? "var(--sidebar-active-bg)" : "#EF444411",
              border: `1px solid ${availableSeats > 0 ? "var(--card-border)" : "#EF444444"}`,
              borderRadius: 8,
              fontSize: 13,
            }}>
              <span style={{ color: "var(--text-muted)" }}>Seats available</span>
              <span style={{
                fontWeight: 700,
                color: availableSeats > 0 ? "var(--main-text)" : "#EF4444",
                fontVariantNumeric: "tabular-nums",
              }}>
                {availableSeats} / {userLimit}
              </span>
            </div>

            {!result ? (
              <>
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <label style={{ fontSize: 13, color: "var(--text-muted)" }}>
                    Paste email addresses — one per line, or separated by commas
                  </label>
                  <textarea
                    value={text}
                    onChange={e => setText(e.target.value)}
                    placeholder={"alice@example.com\nbob@example.com\ncarol@example.com"}
                    rows={6}
                    style={{
                      padding: "0.65rem 0.75rem",
                      borderRadius: 8,
                      border: "1px solid var(--card-border)",
                      background: "var(--main-bg)",
                      color: "var(--main-text)",
                      fontSize: 13,
                      fontFamily: "monospace",
                      resize: "vertical",
                      outline: "none",
                    }}
                  />
                  {emails.length > 0 && (
                    <div style={{ fontSize: 12, color: "var(--text-muted)", display: "flex", gap: 12 }}>
                      <span>{emails.length} email{emails.length !== 1 ? "s" : ""} detected</span>
                      {overCount > 0 && (
                        <span style={{ color: "#F59E0B" }}>
                          {overCount} will be skipped (seat limit)
                        </span>
                      )}
                    </div>
                  )}
                </div>

                {availableSeats <= 0 && (
                  <p style={{ margin: 0, fontSize: 13, color: "#EF4444" }}>
                    No seats available on your current plan. Upgrade to add more users.
                  </p>
                )}

                <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
                  <button
                    onClick={close}
                    style={{
                      padding: "0.5rem 1rem", borderRadius: 8,
                      border: "1px solid var(--card-border)",
                      background: "var(--main-bg)", color: "var(--main-text)",
                      fontSize: 13, cursor: "pointer",
                    }}
                  >
                    Cancel
                  </button>
                  <button
                    onClick={submit}
                    disabled={isPending || capped.length === 0 || availableSeats <= 0}
                    style={{
                      padding: "0.5rem 1.25rem", borderRadius: 8,
                      border: "none",
                      background: capped.length > 0 && !isPending && availableSeats > 0
                        ? "var(--accent)" : "var(--text-muted)",
                      color: "#fff",
                      fontSize: 13, fontWeight: 600,
                      cursor: capped.length > 0 && !isPending && availableSeats > 0 ? "pointer" : "not-allowed",
                    }}
                  >
                    {isPending ? "Importing…" : `Import ${capped.length || ""} User${capped.length !== 1 ? "s" : ""}`}
                  </button>
                </div>
              </>
            ) : (
              <>
                {result.error ? (
                  <p style={{ margin: 0, fontSize: 13, color: "#EF4444" }}>{result.error}</p>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                    {result.imported.length > 0 && (
                      <div style={{
                        padding: "0.75rem 1rem",
                        borderRadius: 8,
                        background: "#10B98111",
                        border: "1px solid #10B98133",
                      }}>
                        <div style={{ fontSize: 13, fontWeight: 600, color: "#10B981", marginBottom: 6 }}>
                          {result.imported.length} user{result.imported.length !== 1 ? "s" : ""} imported
                        </div>
                        {result.imported.map(e => (
                          <div key={e} style={{ fontSize: 12, color: "var(--text-muted)", fontFamily: "monospace" }}>{e}</div>
                        ))}
                      </div>
                    )}
                    {result.skipped.length > 0 && (
                      <div style={{
                        padding: "0.75rem 1rem",
                        borderRadius: 8,
                        background: "#F59E0B11",
                        border: "1px solid #F59E0B33",
                      }}>
                        <div style={{ fontSize: 13, fontWeight: 600, color: "#F59E0B", marginBottom: 6 }}>
                          {result.skipped.length} skipped
                        </div>
                        {result.skipped.map(s => (
                          <div key={s.email} style={{ fontSize: 12, color: "var(--text-muted)", fontFamily: "monospace" }}>
                            {s.email} <span style={{ color: "var(--text-muted)", opacity: 0.7 }}>— {s.reason}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
                <div style={{ display: "flex", justifyContent: "flex-end" }}>
                  <button
                    onClick={close}
                    style={{
                      padding: "0.5rem 1.25rem", borderRadius: 8,
                      border: "none", background: "var(--accent)", color: "#fff",
                      fontSize: 13, fontWeight: 600, cursor: "pointer",
                    }}
                  >
                    Done
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </>
  )
}
