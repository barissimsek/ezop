import { auth } from "@/auth"
import { prisma } from "@/lib/prisma"
import Card from "@/components/Card"
import AgentActivityChart from "@/components/charts/AgentActivityChart"
import SuccessFailureChart from "@/components/charts/SuccessFailureChart"
import CostChart from "@/components/charts/CostChart"
import PromptVersionChart from "@/components/charts/PromptVersionChart"
import PerformanceFilters from "@/components/PerformanceFilters"

const DAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

type Run = { id: string; start_time: Date; status: string; version_id: string | null; agent_id: string }

export default async function AgentPerformancePage({
  searchParams,
}: {
  searchParams: Promise<{ timeRange?: string; agentId?: string }>
}) {
  const { timeRange: timeRangeParam, agentId: agentIdParam } = await searchParams
  const session = await auth()

  const user = await prisma.user.findUnique({
    where: { email: session!.user!.email! },
    select: { memberships: { select: { organization_id: true }, take: 1 } },
  })

  const orgId = user?.memberships[0]?.organization_id ?? null

  // Fetch agents for the filter dropdown
  const agentRows: { id: string; name: string }[] = orgId
    ? await prisma.agent.findMany({
        where: { organization_id: orgId },
        select: { id: true, name: true },
        orderBy: { name: "asc" },
      })
    : []

  const agents = agentRows

  const timeRange = timeRangeParam ?? "7"
  const agentId = agentIdParam ?? ""
  const days = Math.max(1, Number(timeRange) || 7)

  // Build UTC-based date range
  const now = new Date()
  const todayUTC = new Date(
    Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()),
  )
  const since = new Date(todayUTC)
  since.setUTCDate(todayUTC.getUTCDate() - (days - 1))

  const [runsRaw, serviceCostsRaw, versionsRaw] = await Promise.all([
    orgId
      ? prisma.agentRun.findMany({
          where: {
            organization_id: orgId,
            start_time: { gte: since },
            ...(agentId ? { agent_id: agentId } : {}),
          },
          select: { id: true, start_time: true, status: true, version_id: true, agent_id: true },
        })
      : Promise.resolve([]),
    prisma.serviceCost.findMany({
      where: { service_type: "llm" },
      select: { service_name: true, unit_cost: true },
    }),
    orgId
      ? prisma.agentVersion.findMany({
          where: {
            organization_id: orgId,
            ...(agentId ? { agent_id: agentId } : {}),
          },
          select: { id: true, agent_id: true, version: true, created_at: true },
          orderBy: { created_at: "desc" },
        })
      : Promise.resolve([]),
  ])

  const runs = runsRaw as Run[]
  const runIds = runs.map(r => r.id)

  // Fetch LLM events
  const llmEvents: { timestamp: Date | null; metadata: unknown }[] = orgId
    ? await prisma.event.findMany({
        where: {
          organization_id: orgId,
          category: "llm",
          timestamp: { gte: since },
          ...(agentId && runIds.length > 0 ? { run_id: { in: runIds } } : agentId ? { run_id: "none" } : {}),
        },
        select: { timestamp: true, metadata: true },
      })
    : []

  // model → unit_cost per 1000 tokens
  const costPerModel: Record<string, number> = {}
  for (const row of serviceCostsRaw) {
    costPerModel[row.service_name] = Number(row.unit_cost)
  }

  console.log("[cost-debug] DATABASE_URL:", process.env.DATABASE_URL)
  console.log("[cost-debug] orgId:", orgId)
  console.log("[cost-debug] llmEvents count:", llmEvents.length)
  console.log("[cost-debug] costPerModel:", costPerModel)
  console.log("[cost-debug] all events:", JSON.stringify(llmEvents, null, 2))

  const statusCounts = {
    running:  runs.filter(r => r.status === "running").length,
    success:  runs.filter(r => r.status === "success").length,
    failed:   runs.filter(r => r.status === "failed").length,
    partial:  runs.filter(r => r.status === "partial").length,
    canceled: runs.filter(r => r.status === "canceled").length,
  }

  // Activity chart
  const activityData = Array.from({ length: days }, (_, i) => {
    const day = new Date(since)
    day.setUTCDate(since.getUTCDate() + i)
    const dayStr = day.toISOString().slice(0, 10)
    const dayRuns = runs.filter(r => r.start_time.toISOString().slice(0, 10) === dayStr)
    return {
      time: DAY_LABELS[day.getUTCDay()],
      running:  dayRuns.filter(r => r.status === "running").length,
      success:  dayRuns.filter(r => r.status === "success").length,
      failed:   dayRuns.filter(r => r.status === "failed").length,
      partial:  dayRuns.filter(r => r.status === "partial").length,
      canceled: dayRuns.filter(r => r.status === "canceled").length,
    }
  })

  // Cost chart
  const costData = Array.from({ length: days }, (_, i) => {
    const day = new Date(since)
    day.setUTCDate(since.getUTCDate() + i)
    const dayStr = day.toISOString().slice(0, 10)
    const llmCost = llmEvents
      .filter(e => e.timestamp?.toISOString().slice(0, 10) === dayStr)
      .reduce((sum, e) => {
        const meta = e.metadata as { model?: string; input_tokens?: number; output_tokens?: number; usage?: { input_tokens?: number; output_tokens?: number } } | null
        if (!meta) return sum
        const unitCost = costPerModel[meta.model ?? ""] ?? 0
        const inputTokens = meta.input_tokens ?? meta.usage?.input_tokens ?? 0
        const outputTokens = meta.output_tokens ?? meta.usage?.output_tokens ?? 0
        const tokens = inputTokens + outputTokens
        return sum + (tokens / 1000) * unitCost
      }, 0)
    return {
      time: DAY_LABELS[day.getUTCDay()],
      llmCost: Math.round(llmCost * 100000) / 100000,
    }
  })

  // Prompt/version chart
  const versionsByAgent: Record<string, { id: string; version: string }[]> = {}
  for (const v of [...versionsRaw].reverse()) {
    if (!versionsByAgent[v.agent_id]) versionsByAgent[v.agent_id] = []
    if (versionsByAgent[v.agent_id].length < 3) {
      versionsByAgent[v.agent_id].push({ id: v.id, version: v.version })
    }
  }

  const maxSlots = Math.min(
    3,
    Math.max(0, ...Object.values(versionsByAgent).map(vs => vs.length)),
  )
  const versionSlotLabels = Array.from({ length: maxSlots }, (_, i) => `v${i + 1}`)

  const promptData = agents
    .filter(a => agentId ? a.id === agentId : true)
    .map(agent => {
      const versions = versionsByAgent[agent.id] ?? []
      const entry: Record<string, string | number> = { agent: agent.name }
      versions.forEach((v, i) => {
        const vRuns = runs.filter(r => r.version_id === v.id && r.agent_id === agent.id)
        const completed = vRuns.filter(r => r.status !== "running")
        const success = vRuns.filter(r => r.status === "success")
        entry[`v${i + 1}`] = completed.length > 0
          ? Math.round((success.length / completed.length) * 100)
          : 0
      })
      return entry
    })

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700 }}>Agent Performance</h1>
          <p style={{ color: "var(--text-muted)", marginTop: "0.25rem", fontSize: "0.9rem" }}>
            Reliability, cost, errors, and behavior across all agents
          </p>
        </div>
        <PerformanceFilters agents={agents} timeRange={timeRange} agentId={agentId} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(480px, 1fr))", gap: "1.5rem" }}>
        <Card title="Agent Activity Over Time" description="Are your agents alive or dead today?">
          <AgentActivityChart data={activityData} />
        </Card>

        <Card title="Success vs Failure Rate" description="Agent reliability breakdown">
          <SuccessFailureChart counts={statusCounts} />
        </Card>

        <Card title="Token & Cost Consumption" description="Which agent is lighting your credit card on fire">
          <CostChart data={costData} />
        </Card>

        <Card title="Prompt / Version Performance" description="Real prompt A/B testing — success rate across agent versions">
          <PromptVersionChart data={promptData} versions={versionSlotLabels} />
        </Card>
      </div>
    </div>
  )
}
