import { getOrgContext } from "@/lib/db/getOrgContext";
import { prisma } from "@/lib/prisma";
import UserFilters from "@/components/UserFilters";
import ImportUsersModal from "@/components/ImportUsersModal";
import UserActionsMenu from "@/components/UserActionsMenu";

export default async function UsersPage({
  searchParams,
}: {
  searchParams: Promise<{ search?: string; pageSize?: string; page?: string }>;
}) {
  const {
    search: searchParam,
    pageSize: pageSizeParam,
    page: pageParam,
  } = await searchParams;

  const { organizationId, userId } = await getOrgContext();

  const search = searchParam ?? "";
  const pageSize = Math.max(1, parseInt(pageSizeParam ?? "10") || 10);
  const page = Math.max(1, parseInt(pageParam ?? "1") || 1);

  // Get memberships for this org
  const memberRows = await prisma.organizationMember.findMany({
    where: { organization_id: organizationId },
    select: { user_id: true, role: true },
  });

  const memberIds = memberRows.map((m: (typeof memberRows)[0]) => m.user_id);
  const roleMap = Object.fromEntries(
    memberRows.map((m: (typeof memberRows)[0]) => [m.user_id, m.role]),
  );
  const isOwner = roleMap[userId] === "owner";

  // Fetch plan limits
  const org = await prisma.organization.findUnique({
    where: { id: organizationId },
    select: { plan: true },
  });

  const planRow = await prisma.plan.findUnique({
    where: { name: org?.plan ?? "free" },
    select: { limits: true },
  });

  const userLimit = (planRow?.limits as { users?: number } | null)?.users ?? 3;
  const availableSeats = Math.max(0, userLimit - memberIds.length);

  // Fetch users with optional search
  const where = {
    id: { in: memberIds.length ? memberIds : [""] },
    ...(search
      ? {
          OR: [
            { email: { contains: search, mode: "insensitive" as const } },
            { firstname: { contains: search, mode: "insensitive" as const } },
            { lastname: { contains: search, mode: "insensitive" as const } },
          ],
        }
      : {}),
  };

  const [users, total] = await Promise.all([
    prisma.user.findMany({
      where,
      select: { id: true, email: true, firstname: true, lastname: true },
      skip: (page - 1) * pageSize,
      take: pageSize,
    }),
    prisma.user.count({ where }),
  ]);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div
      style={{
        padding: "2rem",
        display: "flex",
        flexDirection: "column",
        gap: "1.5rem",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <h1
          style={{
            fontSize: "1.4rem",
            fontWeight: 700,
            color: "var(--main-text)",
            margin: 0,
          }}
        >
          Users
        </h1>
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <ImportUsersModal
            isOwner={isOwner}
            availableSeats={availableSeats}
            userLimit={userLimit}
          />
        </div>
      </div>

      <div
        style={{
          background: "var(--card-bg)",
          border: "1px solid var(--card-border)",
          borderRadius: 12,
          overflow: "hidden",
        }}
      >
        {/* Filters */}
        <div
          style={{
            padding: "1rem 1.25rem",
            borderBottom: "1px solid var(--card-border)",
          }}
        >
          <UserFilters search={search} pageSize={pageSize} />
        </div>

        {/* Table */}
        <table
          style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}
        >
          <thead>
            <tr style={{ background: "var(--main-bg)" }}>
              {["Name", "Email", ""].map((h) => (
                <th
                  key={h}
                  style={{
                    padding: "0.6rem 1.25rem",
                    textAlign: "left",
                    fontSize: 11,
                    fontWeight: 600,
                    color: "var(--text-muted)",
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                    borderBottom: "1px solid var(--card-border)",
                  }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {users.length === 0 ? (
              <tr>
                <td
                  colSpan={3}
                  style={{
                    padding: "3rem",
                    textAlign: "center",
                    color: "var(--text-muted)",
                  }}
                >
                  No users found.
                </td>
              </tr>
            ) : (
              users.map((u: (typeof users)[0]) => (
                <tr
                  key={u.id}
                  style={{ borderBottom: "1px solid var(--card-border)" }}
                >
                  <td
                    style={{
                      padding: "0.75rem 1.25rem",
                      color: "var(--main-text)",
                      fontWeight: 500,
                    }}
                  >
                    {u.firstname || u.lastname ? (
                      `${u.firstname ?? ""} ${u.lastname ?? ""}`.trim()
                    ) : (
                      <span style={{ color: "var(--text-muted)" }}>—</span>
                    )}
                  </td>
                  <td
                    style={{
                      padding: "0.75rem 1.25rem",
                      color: "var(--text-muted)",
                      fontFamily: "monospace",
                      fontSize: 12,
                    }}
                  >
                    {u.email}
                  </td>
                  <td
                    style={{
                      padding: "0.75rem 1rem",
                      textAlign: "right",
                      width: 48,
                    }}
                  >
                    {roleMap[u.id] !== "owner" && (
                      <UserActionsMenu userId={u.id} isOwner={isOwner} />
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>

        {/* Pagination */}
        <Pagination
          page={page}
          totalPages={totalPages}
          total={total}
          pageSize={pageSize}
        />
      </div>
    </div>
  );
}

function Pagination({
  page,
  totalPages,
  total,
  pageSize,
}: {
  page: number;
  totalPages: number;
  total: number;
  pageSize: number;
}) {
  const from = Math.min((page - 1) * pageSize + 1, total);
  const to = Math.min(page * pageSize, total);

  function href(p: number) {
    return `?page=${p}&pageSize=${pageSize}`;
  }

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0.75rem 1.25rem",
        borderTop: "1px solid var(--card-border)",
        fontSize: 12,
        color: "var(--text-muted)",
      }}
    >
      <span>{total > 0 ? `${from}–${to} of ${total}` : "0 results"}</span>
      <div style={{ display: "flex", gap: "0.375rem" }}>
        {[
          { label: "←", p: page - 1, disabled: page <= 1 },
          { label: "→", p: page + 1, disabled: page >= totalPages },
        ].map((btn) =>
          btn.disabled ? (
            <span
              key={btn.label}
              style={{
                padding: "0.3rem 0.65rem",
                borderRadius: 6,
                border: "1px solid var(--card-border)",
                color: "var(--card-border)",
                userSelect: "none",
              }}
            >
              {btn.label}
            </span>
          ) : (
            <a
              key={btn.label}
              href={href(btn.p)}
              style={{
                padding: "0.3rem 0.65rem",
                borderRadius: 6,
                border: "1px solid var(--card-border)",
                color: "var(--main-text)",
                textDecoration: "none",
              }}
            >
              {btn.label}
            </a>
          ),
        )}
      </div>
    </div>
  );
}
