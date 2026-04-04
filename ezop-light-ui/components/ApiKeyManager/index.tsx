"use client"

import { useState, useTransition } from "react"
import { useRouter } from "next/navigation"
import type { ApiKey } from "@/app/dashboard/api-keys/actions"
import { createApiKey, revokeApiKey, rotateApiKey, deleteApiKey } from "@/app/dashboard/api-keys/actions"

// ─── Constants ────────────────────────────────────────────────────────────────

const ALL_SCOPES = [
  { value: "runs:read",    label: "Runs — Read"    },
  { value: "runs:write",   label: "Runs — Write"   },
  { value: "agents:read",  label: "Agents — Read"  },
  { value: "agents:write", label: "Agents — Write" },
  { value: "logs:read",    label: "Logs — Read"    },
  { value: "metrics:read", label: "Metrics — Read" },
]

const EXPIRY_OPTIONS = [
  { label: "No expiry",  value: null },
  { label: "30 days",    value: 30   },
  { label: "90 days",    value: 90   },
  { label: "180 days",   value: 180  },
  { label: "1 year",     value: 365  },
]

// ─── Helpers ──────────────────────────────────────────────────────────────────

function relativeTime(iso: string | null): string {
  if (!iso) return "Never"
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1)   return "just now"
  if (mins < 60)  return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24)   return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—"
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
}

function isExpired(iso: string | null): boolean {
  return !!iso && new Date(iso) < new Date()
}

function keyStatus(key: ApiKey): { label: string; color: string } {
  if (key.revoked_at)            return { label: "revoked",  color: "#EF4444" }
  if (isExpired(key.expires_at)) return { label: "expired",  color: "#F59E0B" }
  return { label: "active", color: "#10B981" }
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function ScopeBadge({ scope }: { scope: string }) {
  return (
    <span style={{
      display: "inline-block", padding: "1px 7px", borderRadius: 99,
      fontSize: 10, fontFamily: "monospace", fontWeight: 500,
      background: "var(--sidebar-active-bg)", color: "var(--accent)",
      border: "1px solid var(--card-border)",
    }}>
      {scope}
    </span>
  )
}

function StatusBadge({ label, color }: { label: string; color: string }) {
  return (
    <span style={{
      display: "inline-block", padding: "2px 8px", borderRadius: 99,
      fontSize: 11, fontWeight: 500,
      background: color + "22", color,
    }}>
      {label}
    </span>
  )
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  function copy() {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }
  return (
    <button onClick={copy} style={{
      padding: "0.3rem 0.7rem", borderRadius: 6, border: "1px solid var(--card-border)",
      background: "transparent", color: copied ? "#10B981" : "var(--text-muted)",
      cursor: "pointer", fontSize: 12, fontWeight: 500, flexShrink: 0,
    }}>
      {copied ? "Copied!" : "Copy"}
    </button>
  )
}

// ─── Revealed Key Banner ──────────────────────────────────────────────────────

function RevealedKeyBanner({ rawKey, onDismiss }: { rawKey: string; onDismiss: () => void }) {
  return (
    <div style={{
      padding: "1rem 1.25rem",
      borderRadius: 10,
      border: "1px solid #F59E0B66",
      background: "#F59E0B11",
      display: "flex",
      flexDirection: "column",
      gap: "0.6rem",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: "#F59E0B" }}>
          ⚠ Copy your key now — it will never be shown again
        </span>
        <button onClick={onDismiss} style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", fontSize: 18, lineHeight: 1 }}>×</button>
      </div>
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <code style={{
          flex: 1, padding: "0.5rem 0.75rem", borderRadius: 6,
          background: "var(--card-bg)", border: "1px solid var(--card-border)",
          fontSize: 13, fontFamily: "monospace", color: "var(--main-text)",
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
        }}>
          {rawKey}
        </code>
        <CopyButton text={rawKey} />
      </div>
    </div>
  )
}

// ─── Create Modal ─────────────────────────────────────────────────────────────

function CreateModal({
  onClose,
  onCreated,
}: {
  onClose: () => void
  onCreated: (rawKey: string) => void
}) {
  const [name, setName]            = useState("")
  const [description, setDesc]     = useState("")
  const [scopes, setScopes]        = useState<string[]>(["runs:read", "agents:read"])
  const [expiresIn, setExpiresIn]  = useState<number | null>(null)
  const [error, setError]          = useState("")
  const [pending, startTransition] = useTransition()

  function toggleScope(s: string) {
    setScopes(prev => prev.includes(s) ? prev.filter(x => x !== s) : [...prev, s])
  }

  function submit() {
    if (!name.trim()) { setError("Name is required"); return }
    if (scopes.length === 0) { setError("Select at least one scope"); return }
    setError("")
    startTransition(async () => {
      try {
        const { rawKey } = await createApiKey(name.trim(), description.trim(), scopes, expiresIn)
        onCreated(rawKey)
        onClose()
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to create key")
      }
    })
  }

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 50,
      background: "rgba(0,0,0,0.5)", backdropFilter: "blur(2px)",
      display: "flex", alignItems: "center", justifyContent: "center", padding: "1rem",
    }}>
      <div style={{
        background: "var(--card-bg)", border: "1px solid var(--card-border)",
        borderRadius: 14, padding: "1.75rem", width: "100%", maxWidth: 480,
        display: "flex", flexDirection: "column", gap: "1.25rem",
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h2 style={{ fontSize: "1.1rem", fontWeight: 700, color: "var(--main-text)" }}>Create API Key</h2>
          <button onClick={onClose} style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", fontSize: 22, lineHeight: 1 }}>×</button>
        </div>

        {/* Name */}
        <Field label="Key Name" required>
          <input
            value={name} onChange={e => setName(e.target.value)}
            placeholder="e.g. Production Backend"
            style={inputStyle}
          />
        </Field>

        {/* Description */}
        <Field label="Description">
          <input
            value={description} onChange={e => setDesc(e.target.value)}
            placeholder="Optional — what is this key for?"
            style={inputStyle}
          />
        </Field>

        {/* Scopes */}
        <Field label="Scopes" required>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {ALL_SCOPES.map(s => {
              const active = scopes.includes(s.value)
              return (
                <button
                  key={s.value}
                  onClick={() => toggleScope(s.value)}
                  style={{
                    padding: "4px 10px", borderRadius: 99, fontSize: 12,
                    fontFamily: "monospace", cursor: "pointer", fontWeight: 500,
                    border: `1px solid ${active ? "var(--accent)" : "var(--card-border)"}`,
                    background: active ? "var(--sidebar-active-bg)" : "transparent",
                    color: active ? "var(--accent)" : "var(--text-muted)",
                    transition: "all 0.1s",
                  }}
                >
                  {s.value}
                </button>
              )
            })}
          </div>
        </Field>

        {/* Expiry */}
        <Field label="Expiry">
          <select
            value={expiresIn ?? ""}
            onChange={e => setExpiresIn(e.target.value === "" ? null : Number(e.target.value))}
            style={inputStyle}
          >
            {EXPIRY_OPTIONS.map(o => (
              <option key={String(o.value)} value={o.value ?? ""}>{o.label}</option>
            ))}
          </select>
        </Field>

        {error && <p style={{ fontSize: 13, color: "#EF4444", margin: 0 }}>{error}</p>}

        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button onClick={onClose} style={{ ...btnStyle, background: "transparent", border: "1px solid var(--card-border)", color: "var(--text-muted)" }}>
            Cancel
          </button>
          <button onClick={submit} disabled={pending} style={{ ...btnStyle, background: "var(--accent)", color: "#fff", border: "none", opacity: pending ? 0.7 : 1 }}>
            {pending ? "Creating…" : "Create Key"}
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Confirm Revoke Modal ─────────────────────────────────────────────────────

function RevokeModal({ keyName, onConfirm, onClose }: { keyName: string; onConfirm: () => void; onClose: () => void }) {
  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 50,
      background: "rgba(0,0,0,0.5)", backdropFilter: "blur(2px)",
      display: "flex", alignItems: "center", justifyContent: "center", padding: "1rem",
    }}>
      <div style={{
        background: "var(--card-bg)", border: "1px solid var(--card-border)",
        borderRadius: 14, padding: "1.75rem", width: "100%", maxWidth: 400,
        display: "flex", flexDirection: "column", gap: "1rem",
      }}>
        <h2 style={{ fontSize: "1.05rem", fontWeight: 700, color: "#EF4444" }}>Revoke API Key</h2>
        <p style={{ fontSize: 14, color: "var(--main-text)", lineHeight: 1.6 }}>
          Are you sure you want to revoke <strong>{keyName}</strong>?
          Any application using this key will immediately lose access. This cannot be undone.
        </p>
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button onClick={onClose} style={{ ...btnStyle, background: "transparent", border: "1px solid var(--card-border)", color: "var(--text-muted)" }}>Cancel</button>
          <button onClick={onConfirm} style={{ ...btnStyle, background: "#EF4444", color: "#fff", border: "none" }}>Revoke</button>
        </div>
      </div>
    </div>
  )
}

// ─── Shared styles ────────────────────────────────────────────────────────────

const inputStyle: React.CSSProperties = {
  width: "100%", padding: "0.55rem 0.75rem",
  border: "1px solid var(--card-border)", borderRadius: 7,
  background: "var(--main-bg)", color: "var(--main-text)",
  fontSize: 13, outline: "none",
}

const btnStyle: React.CSSProperties = {
  padding: "0.5rem 1.1rem", borderRadius: 7, cursor: "pointer",
  fontSize: 13, fontWeight: 500,
}

function Field({ label, required, children }: { label: string; required?: boolean; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted)" }}>
        {label}{required && <span style={{ color: "#EF4444" }}> *</span>}
      </label>
      {children}
    </div>
  )
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function ApiKeyManager({ initialKeys }: { initialKeys: ApiKey[] }) {
  const [keys, setKeys]                 = useState<ApiKey[]>(initialKeys)
  const [showCreate, setShowCreate]     = useState(false)
  const [revokeTarget, setRevokeTarget] = useState<ApiKey | null>(null)
  const [revealedKey, setRevealedKey]   = useState<string | null>(null)
  const [rotatedKey, setRotatedKey]     = useState<string | null>(null)
  const [pending, startTransition]      = useTransition()
  const router = useRouter()

  function handleCreated(rawKey: string) {
    setRevealedKey(rawKey)
    startTransition(() => { router.refresh() })
  }

  function handleRevoke() {
    if (!revokeTarget) return
    const id = revokeTarget.id
    setRevokeTarget(null)
    startTransition(async () => {
      await revokeApiKey(id)
      setKeys(prev => prev.map(k => k.id === id ? { ...k, revoked_at: new Date().toISOString() } : k))
    })
  }

  function handleRotate(key: ApiKey) {
    startTransition(async () => {
      const { rawKey } = await rotateApiKey(key.id)
      setRotatedKey(rawKey)
      router.refresh()
    })
  }

  const activeCount  = keys.filter(k => !k.revoked_at && !isExpired(k.expires_at)).length
  const revokedCount = keys.filter(k => !!k.revoked_at).length

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>

      {/* Revealed key banners */}
      {revealedKey && <RevealedKeyBanner rawKey={revealedKey} onDismiss={() => setRevealedKey(null)} />}
      {rotatedKey  && <RevealedKeyBanner rawKey={rotatedKey}  onDismiss={() => setRotatedKey(null)}  />}

      {/* Toolbar */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
        <div style={{ display: "flex", gap: "1.25rem" }}>
          <Stat label="Active"  value={activeCount}  color="#10B981" />
          <Stat label="Revoked" value={revokedCount} color="#EF4444" />
          <Stat label="Total"   value={keys.length}  color="var(--text-muted)" />
        </div>
        <button
          onClick={() => setShowCreate(true)}
          style={{ ...btnStyle, background: "var(--accent)", color: "#fff", border: "none" }}
        >
          + Create API Key
        </button>
      </div>

      {/* Table */}
      <div style={{ background: "var(--card-bg)", border: "1px solid var(--card-border)", borderRadius: 12, overflow: "hidden" }}>
        {/* Header */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 170px 1fr 100px 100px 100px 130px", gap: "0.5rem", padding: "0.65rem 1.25rem", borderBottom: "1px solid var(--card-border)" }}>
          {["Name", "Key", "Scopes", "Status", "Last Used", "Expires", "Actions"].map(h => (
            <div key={h} style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-muted)" }}>{h}</div>
          ))}
        </div>

        {keys.length === 0 && (
          <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)", fontSize: 14 }}>
            No API keys yet. Create one to get started.
          </div>
        )}

        {keys.map((key, i) => {
          const status   = keyStatus(key)
          const isActive = status.label === "active"
          return (
            <div
              key={key.id}
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 170px 1fr 100px 100px 100px 130px",
                gap: "0.5rem",
                padding: "0.9rem 1.25rem",
                borderBottom: i < keys.length - 1 ? "1px solid var(--card-border)" : "none",
                alignItems: "center",
                opacity: isActive ? 1 : 0.55,
              }}
            >
              {/* Name + description */}
              <div>
                <div style={{ fontWeight: 600, fontSize: 14, color: "var(--main-text)" }}>{key.name}</div>
                {key.description && (
                  <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>{key.description}</div>
                )}
              </div>

              {/* Key prefix */}
              <code style={{ fontSize: 12, fontFamily: "monospace", color: "var(--text-muted)", background: "var(--sidebar-active-bg)", padding: "3px 8px", borderRadius: 4, whiteSpace: "nowrap" }}>
                {key.key_prefix}…
              </code>

              {/* Scopes */}
              <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                {key.scopes.map(s => <ScopeBadge key={s} scope={s} />)}
              </div>

              {/* Status */}
              <div><StatusBadge label={status.label} color={status.color} /></div>

              {/* Last used */}
              <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{relativeTime(key.last_used_at)}</div>

              {/* Expires */}
              <div style={{ fontSize: 12, color: isExpired(key.expires_at) ? "#F59E0B" : "var(--text-muted)" }}>
                {fmtDate(key.expires_at)}
              </div>

              {/* Actions */}
              <div style={{ display: "flex", gap: 6 }}>
                {isActive && (
                  <>
                    <ActionBtn label="Rotate" color="#06B6D4" disabled={pending} onClick={() => handleRotate(key)} />
                    <ActionBtn label="Revoke" color="#EF4444" disabled={pending} onClick={() => setRevokeTarget(key)} />
                  </>
                )}
                {!isActive && (
                  <ActionBtn
                    label="Delete"
                    color="#EF4444"
                    disabled={pending}
                    onClick={() => {
                      startTransition(async () => {
                        await deleteApiKey(key.id)
                        setKeys(prev => prev.filter(k => k.id !== key.id))
                      })
                    }}
                  />
                )}
              </div>
            </div>
          )
        })}
      </div>

      <p style={{ fontSize: 11, color: "var(--text-muted)", textAlign: "right", fontFamily: "monospace" }}>
        Keys are hashed with SHA-256. Raw values are never stored.
      </p>

      {/* Modals */}
      {showCreate && (
        <CreateModal onClose={() => setShowCreate(false)} onCreated={handleCreated} />
      )}
      {revokeTarget && (
        <RevokeModal keyName={revokeTarget.name} onConfirm={handleRevoke} onClose={() => setRevokeTarget(null)} />
      )}
    </div>
  )
}

function Stat({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div style={{ display: "flex", alignItems: "baseline", gap: 5 }}>
      <span style={{ fontSize: "1.25rem", fontWeight: 700, color, fontVariantNumeric: "tabular-nums" }}>{value}</span>
      <span style={{ fontSize: 12, color: "var(--text-muted)" }}>{label}</span>
    </div>
  )
}

function ActionBtn({ label, color, onClick, disabled }: { label: string; color: string; onClick: () => void; disabled?: boolean }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        padding: "3px 8px", borderRadius: 5,
        border: `1px solid ${color}44`, background: color + "11",
        color, cursor: "pointer", fontSize: 11, fontWeight: 500,
        opacity: disabled ? 0.5 : 1,
      }}
    >
      {label}
    </button>
  )
}
