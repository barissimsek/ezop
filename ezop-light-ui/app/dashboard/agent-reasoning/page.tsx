import { auth } from "@/auth";
import { prisma } from "@/lib/prisma";
import Card from "@/components/Card";
import ReasoningDepthChart from "@/components/charts/ReasoningDepthChart";
import DecisionTraceMap from "@/components/charts/DecisionTraceMap";
import ReasoningFilters from "@/components/ReasoningFilters";

// ─── Types ────────────────────────────────────────────────────────────────────

type Span = {
  id: string;
  run_id: string;
  parent_id: string | null;
  name: string;
  start_time: Date | null;
};

type SpanSignals = {
  categories: Set<string>;
  hasError: boolean;
};

// ─── Span tree depth ──────────────────────────────────────────────────────────

function computeMaxDepth(
  spanId: string,
  children: Record<string, string[]>,
  memo: Record<string, number> = {},
): number {
  if (memo[spanId] !== undefined) return memo[spanId];
  const kids = children[spanId] ?? [];
  if (kids.length === 0) {
    memo[spanId] = 1;
    return 1;
  }
  const depth =
    1 + Math.max(...kids.map((c) => computeMaxDepth(c, children, memo)));
  memo[spanId] = depth;
  return depth;
}

// ─── Step classifier (spans as steps) ────────────────────────────────────────

function classifySpan(
  span: Span,
  signals: SpanSignals,
  isRoot: boolean,
): string {
  if (isRoot) return "task_start";
  const n = span.name.toLowerCase();
  if (signals.categories.has("llm")) return "reasoning";
  if (signals.categories.has("tool")) {
    if (signals.hasError) return "tool_error";
    if (n.includes("retry")) return "retry";
    return "tool_call";
  }
  if (signals.hasError) return "tool_error";
  if (n.includes("reason") || n.includes("plan") || n.includes("think"))
    return "reasoning";
  if (n.includes("retry")) return "retry";
  if (n.includes("valid")) return "validation";
  if (n.includes("tool") || n.includes("invoke") || n.includes("call"))
    return "tool_call";
  if (n.includes("error") || n.includes("fail")) return "tool_error";
  return "reasoning";
}

function normalizeKey(type: string, spanName: string): string {
  if (type === "tool_call" || type === "tool_error") {
    const clean = spanName
      .toLowerCase()
      .replace(/[^a-z0-9_]/g, "_")
      .replace(/_+/g, "_")
      .replace(/^_|_$/g, "")
      .slice(0, 30);
    return `${type}:${clean}`;
  }
  return type;
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default async function AgentReasoningPage({
  searchParams,
}: {
  searchParams: Promise<{ agentId?: string }>;
}) {
  const { agentId: agentIdParam } = await searchParams;
  const agentId = agentIdParam ?? "";

  const session = await auth();

  const user = await prisma.user.findUnique({
    where: { email: session!.user!.email! },
    select: { memberships: { select: { organization_id: true }, take: 1 } },
  });

  const orgId = user?.memberships[0]?.organization_id ?? null;

  // Agents dropdown
  const agentRows: { id: string; name: string }[] = orgId
    ? await prisma.agent.findMany({
        where: { organization_id: orgId },
        select: { id: true, name: true },
        orderBy: { name: "asc" },
      })
    : [];

  const agents = agentRows;
  const resolvedAgentId = agentId || agents[0]?.id || "";

  const nodeCounts: Record<string, number> = {};
  const edgeCounts: Record<string, number> = {};
  let totalRuns = 0;

  type DepthPoint = Record<string, string | number>;
  const depthData: DepthPoint[] = [];
  const agentNames: string[] = [];

  if (orgId) {
    const since = new Date();
    since.setDate(since.getDate() - 30);

    // 1. Completed runs with agent_id
    const runRows: {
      id: string;
      status: string;
      agent_id: string;
      start_time: Date;
    }[] = await prisma.agentRun.findMany({
      where: {
        organization_id: orgId,
        start_time: { gte: since },
        status: { not: "running" },
        ...(resolvedAgentId ? { agent_id: resolvedAgentId } : {}),
      },
      select: { id: true, status: true, agent_id: true, start_time: true },
      take: 500,
    });

    const runMap: Record<
      string,
      { status: string; agentId: string; day: string }
    > = {};
    for (const r of runRows) {
      runMap[r.id] = {
        status: r.status,
        agentId: r.agent_id,
        day: r.start_time.toLocaleDateString("en-US", {
          month: "short",
          day: "numeric",
        }),
      };
    }
    const runIds = Object.keys(runMap);

    if (runIds.length > 0) {
      // 2. Agent names
      const agentIds = [
        ...new Set(runRows.map((r) => r.agent_id).filter(Boolean)),
      ];
      const agentNameRows = await prisma.agent.findMany({
        where: { id: { in: agentIds } },
        select: { id: true, name: true },
      });
      const agentNameMap: Record<string, string> = {};
      for (const a of agentNameRows) agentNameMap[a.id] = a.name;

      // 3. Spans for all runs
      const spansRaw = await prisma.span.findMany({
        where: { run_id: { in: runIds } },
        select: {
          id: true,
          run_id: true,
          parent_id: true,
          name: true,
          start_time: true,
        },
        orderBy: [{ run_id: "asc" }, { start_time: "asc" }],
      });

      const spans: Span[] = spansRaw.map((s: Span) => ({
        id: s.id,
        run_id: s.run_id,
        parent_id: s.parent_id,
        name: s.name,
        start_time: s.start_time,
      }));

      // 4. Event signals per span
      const spanIds = spans.map((s) => s.id);
      const eventSignals: Record<string, SpanSignals> = {};

      if (spanIds.length > 0) {
        const events = await prisma.event.findMany({
          where: {
            span_id: { in: spanIds },
            organization_id: orgId,
          },
          select: { span_id: true, category: true, error: true },
        });

        for (const e of events) {
          if (!e.span_id) continue;
          const sig = (eventSignals[e.span_id] ??= {
            categories: new Set(),
            hasError: false,
          });
          if (e.category) sig.categories.add(e.category);
          if (e.error) sig.hasError = true;
        }
      }

      // 5. Group spans by run
      const byRun: Record<string, Span[]> = {};
      for (const s of spans) (byRun[s.run_id] ??= []).push(s);

      const depthAcc: Record<string, Record<string, number[]>> = {};

      for (const [runId, runSpans] of Object.entries(byRun)) {
        const meta = runMap[runId];
        if (!meta) continue;

        const runSpanIds = new Set(runSpans.map((s) => s.id));

        // ── Depth computation ──
        const children: Record<string, string[]> = {};
        const roots: string[] = [];
        for (const s of runSpans) {
          const isRoot = !s.parent_id || !runSpanIds.has(s.parent_id);
          if (isRoot) {
            roots.push(s.id);
          } else {
            (children[s.parent_id!] ??= []).push(s.id);
          }
        }
        const memo: Record<string, number> = {};
        const runDepth =
          roots.length > 0
            ? Math.max(...roots.map((r) => computeMaxDepth(r, children, memo)))
            : 0;

        const { day, agentId: runAgentId } = meta;
        ((depthAcc[day] ??= {})[runAgentId] ??= []).push(runDepth);

        // ── Trace transitions ──
        const stages: string[] = [];
        for (const span of runSpans) {
          const isRoot = !span.parent_id || !runSpanIds.has(span.parent_id);
          const signals = eventSignals[span.id] ?? {
            categories: new Set(),
            hasError: false,
          };
          const type = classifySpan(span, signals, isRoot);
          const stepKey = normalizeKey(type, span.name);
          if (stepKey !== stages[stages.length - 1]) stages.push(stepKey);
        }

        if (stages.length === 0) stages.push("task_start");

        const terminal =
          meta.status === "success"
            ? "success"
            : meta.status === "partial"
              ? "partial"
              : "failed";
        if (stages[stages.length - 1] !== terminal) stages.push(terminal);

        for (const s of stages) nodeCounts[s] = (nodeCounts[s] ?? 0) + 1;
        for (let i = 0; i < stages.length - 1; i++) {
          const key = `${stages[i]}→${stages[i + 1]}`;
          edgeCounts[key] = (edgeCounts[key] ?? 0) + 1;
        }

        totalRuns++;
      }

      // 6. Build depth chart data
      const uniqueAgents = [
        ...new Set(runRows.map((r) => r.agent_id).filter(Boolean)),
      ]
        .map((id) => ({ id, name: agentNameMap[id] ?? id.slice(0, 8) }))
        .slice(0, 6);

      agentNames.push(...uniqueAgents.map((a) => a.name));

      const allDays = [
        ...new Set(
          runRows.map((r) =>
            r.start_time.toLocaleDateString("en-US", {
              month: "short",
              day: "numeric",
            }),
          ),
        ),
      ].sort((a, b) => new Date(a).getTime() - new Date(b).getTime());

      for (const day of allDays) {
        const point: DepthPoint = { day };
        for (const agent of uniqueAgents) {
          const depths = depthAcc[day]?.[agent.id];
          if (depths && depths.length > 0) {
            point[agent.name] = Math.round(
              depths.reduce((s, d) => s + d, 0) / depths.length,
            );
          }
        }
        depthData.push(point);
      }
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
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
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700 }}>
            Agent Reasoning
          </h1>
          <p
            style={{
              color: "var(--text-muted)",
              marginTop: "0.25rem",
              fontSize: "0.9rem",
            }}
          >
            How your agents reason, decide, and recover
          </p>
        </div>
        <ReasoningFilters agents={agents} agentId={resolvedAgentId} />
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(480px, 1fr))",
          gap: "1.5rem",
        }}
      >
        <Card
          title="Reasoning Depth Curve"
          description="Too shallow fails tasks. Too deep burns tokens. The sweet spot is everything."
          fullWidth
        >
          <ReasoningDepthChart data={depthData} agentNames={agentNames} />
        </Card>

        <Card
          title="Agent Decision Trace Map"
          description="Aggregated map of how your agents think — every path, every branch, every failure"
          fullWidth
        >
          <DecisionTraceMap
            nodeCounts={nodeCounts}
            edgeCounts={edgeCounts}
            totalRuns={totalRuns}
          />
        </Card>
      </div>
    </div>
  );
}
