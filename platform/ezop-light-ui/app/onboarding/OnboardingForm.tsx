"use client"

import { useState, useTransition } from "react"
import { completeOnboarding } from "./actions"

type Props = {
  email: string
  firstName: string
  lastName: string
}

const inputStyle: React.CSSProperties = {
  width: "100%", padding: "0.65rem 0.875rem",
  border: "1px solid var(--card-border)", borderRadius: 8,
  background: "var(--card-bg)", color: "var(--main-text)",
  fontSize: 14, outline: "none", boxSizing: "border-box",
}

const labelStyle: React.CSSProperties = {
  display: "block", fontSize: 12, fontWeight: 600,
  color: "var(--text-muted)", marginBottom: 6,
  textTransform: "uppercase", letterSpacing: "0.04em",
}

export default function OnboardingForm({ email, firstName, lastName }: Props) {
  const [error, setError] = useState<string | null>(null)
  const [isPending, startTransition] = useTransition()

  function handleFormSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setError(null)
    const formData = new FormData(e.currentTarget)
    startTransition(async () => {
      try {
        await completeOnboarding(formData)
      } catch (err) {
        if ((err as { digest?: string })?.digest?.startsWith("NEXT_REDIRECT")) throw err
        setError(err instanceof Error ? err.message : "Something went wrong")
      }
    })
  }

  return (
    <form onSubmit={handleFormSubmit} style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      {/* Name row */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
        <div>
          <label style={labelStyle}>First Name</label>
          <input name="firstName" defaultValue={firstName} required style={inputStyle} />
        </div>
        <div>
          <label style={labelStyle}>Last Name</label>
          <input name="lastName" defaultValue={lastName} required style={inputStyle} />
        </div>
      </div>

      {/* Email — read-only */}
      <div>
        <label style={labelStyle}>Email</label>
        <input value={email} readOnly style={{ ...inputStyle, opacity: 0.6, cursor: "not-allowed" }} />
      </div>

      <div style={{ height: 1, background: "var(--card-border)" }} />

      {/* Org name */}
      <div>
        <label style={labelStyle}>Organization Name</label>
        <input name="orgName" placeholder="Acme Corp" required style={inputStyle} />
        <p style={{ marginTop: 6, fontSize: 12, color: "var(--text-muted)" }}>
          You'll be added as the owner. Team members can be invited later.
        </p>
      </div>

      {error && (
        <div style={{ padding: "0.6rem 0.875rem", borderRadius: 8, background: "#EF444420", border: "1px solid #EF444440", color: "#EF4444", fontSize: 13 }}>
          {error}
        </div>
      )}

      <button
        type="submit"
        disabled={isPending}
        style={{
          padding: "0.75rem", borderRadius: 8, border: "none",
          background: isPending ? "var(--card-border)" : "var(--accent)",
          color: "#fff", fontSize: 15, fontWeight: 600,
          cursor: isPending ? "not-allowed" : "pointer",
          transition: "background 0.15s",
        }}
      >
        {isPending ? "Setting up…" : "Create workspace →"}
      </button>
    </form>
  )
}
