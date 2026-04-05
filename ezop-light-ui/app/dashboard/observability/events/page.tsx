import { auth } from "@/auth";
import { prisma } from "@/lib/prisma";
import EventFilters from "@/components/EventFilters";
import ViewToggle from "@/components/ViewToggle";
import EventTree, {
  type EventNode,
  type SpanNode,
  type RunGroup,
} from "@/components/EventTree";
import EventsTable from "@/components/EventsTable";

function computeSince(timeRange: string): Date {
  const now = new Date();
  const match = timeRange.match(/^(\d+)(m|h|d)$/);
  if (!match) return new Date(now.getTime() - 60 * 60 * 1000);
  const amount = parseInt(match[1]);
  const unit = match[2];
  const ms =
    unit === "m"
      ? amount * 60 * 1000
      : unit === "h"
        ? amount * 60 * 60 * 1000
        : amount * 24 * 60 * 60 * 1000;
  return new Date(now.getTime() - ms);
}

export default async function EventsPage({
  searchParams,
}: {
  searchParams: Promise<{
    timeRange?: string;
    agentId?: string;
    pageSize?: string;
    page?: string;
    view?: string;
  }>;
}) {
  const {
    timeRange: timeRangeParam,
    agentId: agentIdParam,
    pageSize: pageSizeParam,
    page: pageParam,
    view: viewParam,
  } = await searchParams;
  const session = await auth();

  const user = await prisma.user.findUnique({
    where: { email: session!.user!.email! },
    select: { memberships: { select: { organization_id: true }, take: 1 } },
  });

  const orgId = user?.memberships[0]?.organization_id ?? null;

  const timeRange = timeRangeParam ?? "1h";
  const view = (viewParam === "tree" ? "tree" : "flat") as "flat" | "tree";
  const agentId = agentIdParam ?? "";
  const pageSize = Math.max(1, parseInt(pageSizeParam ?? "10") || 10);
  const page = Math.max(1, parseInt(pageParam ?? "1") || 1);
  const since = computeSince(timeRange);

  // Agents dropdown
  const agents: { id: string; name: string }[] = orgId
    ? await prisma.agent.findMany({
        where: { organization_id: orgId },
        select: { id: true, name: true },
        orderBy: { name: "asc" },
      })
    : [];

  const eventSelect = {
    id: true,
    agent_id: true,
    name: true,
    category: true,
    type: true,
    subtype: true,
    timestamp: true,
    run_id: true,
    span_id: true,
    iteration_id: true,
    input: true,
    output: true,
    metadata: true,
    error: true,
  } as const;

  type EventRow = {
    id: string;
    agent_id: string;
    name: string;
    category: string | null;
    type: string | null;
    subtype: string | null;
    timestamp: Date | null;
    run_id: string | null;
    span_id: string | null;
    iteration_id: number | null;
    input: unknown;
    output: unknown;
    metadata: unknown;
    error: unknown;
  };

  let eventsData: EventRow[] = [];
  let total = 0;

  if (orgId) {
    const baseWhere = {
      organization_id: orgId,
      timestamp: { gte: since },
      ...(agentId ? { agent_id: agentId } : {}),
    };

    if (view === "flat") {
      const from = (page - 1) * pageSize;
      [eventsData, total] = await Promise.all([
        prisma.event.findMany({
          where: baseWhere,
          select: eventSelect,
          orderBy: { timestamp: "desc" },
          skip: from,
          take: pageSize,
        }),
        prisma.event.count({ where: baseWhere }),
      ]);
    } else {
      [eventsData, total] = await Promise.all([
        prisma.event.findMany({
          where: baseWhere,
          select: eventSelect,
          orderBy: { timestamp: "asc" },
          take: 500,
        }),
        prisma.event.count({ where: baseWhere }),
      ]);
    }
  }

  // Resolve agent names directly from events.agent_id
  const agentIds = [
    ...new Set(eventsData.map((e) => e.agent_id).filter((id): id is string => Boolean(id))),
  ];
  const agentNameRows: { id: string; name: string }[] =
    agentIds.length > 0
      ? await prisma.agent.findMany({
          where: { id: { in: agentIds } },
          select: { id: true, name: true },
        })
      : [];
  const agentNameById: Record<string, string> = {};
  for (const a of agentNameRows) agentNameById[a.id] = a.name;

  const runToAgent: Record<string, string> = {};
  for (const e of eventsData) {
    if (e.run_id && e.agent_id) runToAgent[e.run_id] = agentNameById[e.agent_id] ?? "—";
  }

  // ── Build tree for hierarchy view ────────────────────────────────────────────
  let runGroups: RunGroup[] = [];

  if (view === "tree" && eventsData.length > 0) {
    const pageRunIds = [
      ...new Set(eventsData.map((e) => e.run_id).filter((id): id is string => Boolean(id))),
    ];
    const spansData = await prisma.span.findMany({
      where: { run_id: { in: pageRunIds } },
      select: {
        id: true,
        parent_id: true,
        name: true,
        run_id: true,
        start_time: true,
      },
    });

    type BuildSpan = SpanNode & { parentId: string | null; runId: string };
    const spanMap = new Map<string, BuildSpan>();
    for (const s of spansData) {
      spanMap.set(s.id, {
        id: s.id,
        spanName: s.name,
        startTime: s.start_time?.toISOString() ?? null,
        parentId: s.parent_id,
        runId: s.run_id,
        events: [],
        children: [],
      });
    }

    const orphansByRun: Record<string, EventNode[]> = {};
    for (const e of eventsData) {
      const eventNode: EventNode = {
        id: e.id,
        name: e.name,
        category: e.category ?? "",
        type: e.type ?? null,
        subtype: e.subtype ?? null,
        timestamp: e.timestamp?.toISOString() ?? "",
        agentName: e.run_id ? (runToAgent[e.run_id] ?? "—") : "—",
        run_id: e.run_id ?? "",
        span_id: e.span_id ?? null,
        iteration_id: e.iteration_id ?? null,
        input: e.input ?? null,
        output: e.output ?? null,
        metadata: e.metadata ?? null,
        error: e.error ?? null,
      };
      if (e.span_id && spanMap.has(e.span_id)) {
        spanMap.get(e.span_id)!.events.push(eventNode);
      } else {
        const rid = e.run_id ?? "";
        if (!orphansByRun[rid]) orphansByRun[rid] = [];
        orphansByRun[rid].push(eventNode);
      }
    }

    const rootSpansByRun: Record<string, SpanNode[]> = {};
    for (const span of spanMap.values()) {
      if (span.parentId && spanMap.has(span.parentId)) {
        spanMap.get(span.parentId)!.children.push(span);
      } else {
        if (!rootSpansByRun[span.runId]) rootSpansByRun[span.runId] = [];
        rootSpansByRun[span.runId].push(span);
      }
    }

    function hasEvents(span: SpanNode): boolean {
      return span.events.length > 0 || span.children.some(hasEvents);
    }
    function pruneSpans(spans: SpanNode[]): SpanNode[] {
      return spans
        .filter(hasEvents)
        .map((s) => ({ ...s, children: pruneSpans(s.children) }))
        .sort((a, b) => (a.startTime ?? "").localeCompare(b.startTime ?? ""));
    }
    for (const runId of Object.keys(rootSpansByRun)) {
      rootSpansByRun[runId] = pruneSpans(rootSpansByRun[runId]);
    }

    const runGroupMap: Record<string, RunGroup> = {};
    for (const runId of pageRunIds) {
      runGroupMap[runId] = {
        runId,
        agentName: runToAgent[runId] ?? "—",
        rootSpans: rootSpansByRun[runId] ?? [],
        rootEvents: orphansByRun[runId] ?? [],
      };
    }
    runGroups = Object.values(runGroupMap);
  }

  const totalPages = Math.ceil(total / pageSize);
  const from = (page - 1) * pageSize;

  // Normalize events for EventsTable (which expects EventDetail shape)
  const eventsForTable = eventsData.map((e) => ({
    ...e,
    timestamp: e.timestamp?.toISOString() ?? "",
    run_id: e.run_id ?? "",
  }));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: "1rem",
        }}
      >
        <div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700 }}>Events</h1>
          <p
            style={{
              color: "var(--text-muted)",
              marginTop: "0.25rem",
              fontSize: "0.9rem",
            }}
          >
            {total.toLocaleString()} event{total !== 1 ? "s" : ""} in selected
            range
          </p>
        </div>
        <EventFilters
          agents={agents}
          timeRange={timeRange}
          agentId={agentId}
          pageSize={pageSize}
        />
      </div>

      {/* View toggle */}
      <div style={{ display: "flex", justifyContent: "flex-end" }}>
        <ViewToggle current={view} />
      </div>

      {/* Tree view */}
      {view === "tree" && <EventTree groups={runGroups} />}

      {/* Flat view */}
      {view === "flat" && (
        <EventsTable events={eventsForTable} runToAgent={runToAgent} />
      )}

      {/* Pagination (flat view only) */}
      {view === "flat" && totalPages > 1 && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            fontSize: 13,
          }}
        >
          <span style={{ color: "var(--text-muted)" }}>
            Showing {from + 1}–{Math.min(from + pageSize, total)} of{" "}
            {total.toLocaleString()}
          </span>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
              const p = i + 1;
              const isActive = p === page;
              return (
                <a
                  key={p}
                  href={`?${new URLSearchParams({ timeRange, agentId, pageSize: String(pageSize), view, page: String(p) }).toString()}`}
                  style={{
                    padding: "0.35rem 0.65rem",
                    borderRadius: 6,
                    fontSize: 13,
                    background: isActive ? "var(--accent)" : "var(--card-bg)",
                    color: isActive ? "#fff" : "var(--main-text)",
                    border: `1px solid ${isActive ? "var(--accent)" : "var(--card-border)"}`,
                    textDecoration: "none",
                  }}
                >
                  {p}
                </a>
              );
            })}
            {totalPages > 7 && (
              <span
                style={{
                  color: "var(--text-muted)",
                  padding: "0.35rem 0.25rem",
                }}
              >
                …
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
