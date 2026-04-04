import { getOrgContext } from "@/lib/db/getOrgContext"
import { prisma } from "@/lib/prisma"
import DangerZoneActions from "./DangerZoneActions"

export default async function DangerZonePage() {
  const { organizationId, userId } = await getOrgContext()

  const membership = await prisma.organizationMember.findFirst({
    where: { organization_id: organizationId, user_id: userId },
    select: { role: true },
  })

  const isOwner = membership?.role === "owner"

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem", maxWidth: 680 }}>
      <div>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--main-text)" }}>Danger Zone</h1>
        <p style={{ color: "var(--text-muted)", marginTop: "0.25rem", fontSize: "0.9rem" }}>
          Irreversible actions. These cannot be undone.
        </p>
      </div>

      {!isOwner && (
        <div style={{
          padding: "0.85rem 1.25rem",
          borderRadius: 10,
          background: "#F59E0B11",
          border: "1px solid #F59E0B44",
          fontSize: 13,
          color: "#F59E0B",
        }}>
          Only the organization owner can perform these actions.
        </div>
      )}

      <DangerZoneActions isOwner={isOwner} />
    </div>
  )
}
