import { getOrgContext } from "@/lib/db/getOrgContext"
import { prisma } from "@/lib/prisma"

function fmt(ts: Date | null) {
  if (!ts) return "—"
  return ts.toLocaleString(undefined, {
    year: "numeric", month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit",
  })
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: "180px 1fr",
      alignItems: "center",
      padding: "0.85rem 1.5rem",
      borderBottom: "1px solid var(--card-border)",
    }}>
      <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
        {label}
      </span>
      <span style={{ fontSize: 14, color: "var(--main-text)" }}>
        {children}
      </span>
    </div>
  )
}

export default async function OrganizationPage() {
  const { organizationId } = await getOrgContext()

  const org = await prisma.organization.findUnique({
    where: { id: organizationId },
    select: {
      id: true,
      name: true,
      updated_at: true,
    },
  })

  if (!org) {
    return (
      <div style={{ padding: "2rem", color: "var(--text-muted)" }}>Organization not found.</div>
    )
  }

  return (
    <div style={{ padding: "2rem", display: "flex", flexDirection: "column", gap: "1.5rem", maxWidth: 760 }}>
      <h1 style={{ fontSize: "1.4rem", fontWeight: 700, color: "var(--main-text)", margin: 0 }}>
        Organization
      </h1>

      <div style={{ background: "var(--card-bg)", border: "1px solid var(--card-border)", borderRadius: 12, overflow: "hidden" }}>
        <Row label="Name">
          {org.name}
        </Row>
        <Row label="ID">
          <span style={{ fontFamily: "monospace", fontSize: 13 }}>{org.id}</span>
        </Row>
        <Row label="Last Updated">
          {fmt(org.updated_at)}
        </Row>
      </div>
    </div>
  )
}
