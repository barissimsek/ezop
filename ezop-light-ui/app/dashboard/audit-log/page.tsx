import { getOrgContext } from "@/lib/db/getOrgContext";
import { prisma } from "@/lib/prisma";
import AuditLog from "@/components/AuditLog";
import type { AuditEntry } from "@/components/AuditLog";

export default async function AuditLogPage() {
  const { organizationId } = await getOrgContext();

  const rows = await prisma.auditLog.findMany({
    where: { organization_id: organizationId },
    select: {
      id: true,
      created_at: true,
      actor_type: true,
      actor_id: true,
      action: true,
      resource_type: true,
      resource_id: true,
      metadata: true,
    },
    orderBy: { created_at: "desc" },
    take: 200,
  });

  // Resolve user actor names/emails in one query
  const actorIds = [
    ...new Set(
      rows
        .map((r: (typeof rows)[0]) => r.actor_id)
        .filter((id: string | null): id is string => Boolean(id)),
    ),
  ];
  const users = actorIds.length
    ? await prisma.user.findMany({
        where: { id: { in: actorIds } },
        select: { id: true, email: true, firstname: true, lastname: true },
      })
    : [];

  const userMap = Object.fromEntries(
    users.map((u: (typeof users)[0]) => [
      u.id,
      {
        name: [u.firstname, u.lastname].filter(Boolean).join(" ") || u.email,
        email: u.email,
      },
    ]),
  );

  const logs: AuditEntry[] = rows.map((row: (typeof rows)[0]) => {
    const meta = (row.metadata ?? {}) as Record<string, unknown>;
    const { target, description, diff, ...rest } = meta;

    const actor =
      row.actor_type === "system" || !row.actor_id
        ? { name: "System", email: "system" }
        : (userMap[row.actor_id] ?? { name: row.actor_id, email: "" });

    return {
      id: row.id,
      ts: row.created_at.toISOString(),
      user: actor.name,
      userEmail: actor.email,
      event: row.action as string,
      resource: row.resource_type ?? "",
      target: (target as string) ?? row.resource_id ?? "—",
      description: (description as string) ?? row.action,
      diff: (diff as AuditEntry["diff"]) ?? undefined,
      meta: Object.keys(rest).length ? rest : undefined,
    };
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <div>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 700 }}>Audit Log</h1>
        <p
          style={{
            color: "var(--text-muted)",
            marginTop: "0.25rem",
            fontSize: "0.9rem",
          }}
        >
          Every change, by every person, in order. Immutable.
        </p>
      </div>

      <AuditLog logs={logs} />
    </div>
  );
}
