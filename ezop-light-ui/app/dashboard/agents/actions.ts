"use server";

import { prisma } from "@/lib/prisma";
import { getOrgContext } from "@/lib/db/getOrgContext";

export type AgentVersion = {
  version: string;
  changelog: string;
  createdAt: string;
};

export type AgentRun = {
  id: string;
  status: "success" | "failed" | "partial" | "running" | "cancelled";
  startTime: string;
  durationS: number;
  triggerType: string;
  triggerId: string | null;
  parentRunId: string | null;
  spawnedRunCount: number;
};

export type Agent = {
  id: string;
  name: string;
  owner: string;
  description: string;
  runtime: string;
  tags: string[];
  status: "active" | "failed" | "paused";
  currentVersion: string;
  successRate: number;
  totalRuns: number;
  lastRunAt: string | null;
  versions: AgentVersion[];
  recentRuns: AgentRun[];
};

export type RunEvent = {
  id: string;
  spanId: string | null;
  parentSpanId: string | null;
  name: string;
  category: string | null;
  timestamp: string | null;
  input: unknown;
  output: unknown;
  error: unknown;
};

export async function listRunEvents(runId: string): Promise<RunEvent[]> {
  const { organizationId } = await getOrgContext();

  const rows = await prisma.event.findMany({
    where: { run_id: runId, organization_id: organizationId },
    orderBy: { timestamp: "asc" },
    select: {
      id: true,
      span_id: true,
      name: true,
      category: true,
      timestamp: true,
      input: true,
      output: true,
      metadata: true,
      error: true,
    },
  });

  return rows.map((e: (typeof rows)[0]) => ({
    id: e.id,
    spanId: e.span_id ?? null,
    parentSpanId:
      (e.metadata as Record<string, string> | null)?.parent_span_id ?? null,
    name: e.name,
    category: e.category ?? null,
    timestamp: e.timestamp?.toISOString() ?? null,
    input: e.input ?? null,
    output: e.output ?? null,
    error: e.error ?? null,
  }));
}

export async function listAgents(): Promise<Agent[]> {
  const { organizationId } = await getOrgContext();

  const [agentRows, versionRows, runRows] = await Promise.all([
    prisma.agent.findMany({
      where: { organization_id: organizationId },
      orderBy: { created_at: "desc" },
      select: {
        id: true,
        name: true,
        owner: true,
        description: true,
        runtime: true,
        created_at: true,
      },
    }),
    prisma.agentVersion.findMany({
      where: { organization_id: organizationId },
      orderBy: { created_at: "desc" },
      select: {
        id: true,
        agent_id: true,
        version: true,
        changelog: true,
        created_at: true,
      },
    }),
    prisma.agentRun.findMany({
      where: { organization_id: organizationId },
      orderBy: { start_time: "desc" },
      take: 500,
      select: {
        id: true,
        agent_id: true,
        status: true,
        start_time: true,
        end_time: true,
        trigger_type: true,
        trigger_id: true,
        parent_run_id: true,
        _count: { select: { spawned_runs: true } },
      },
    }),
  ]);

  if (!agentRows.length) return [];

  return agentRows.map((agent: (typeof agentRows)[0]) => {
    const agentVersions = versionRows.filter(
      (v: (typeof versionRows)[0]) => v.agent_id === agent.id,
    );
    const agentRuns = runRows.filter(
      (r: (typeof runRows)[0]) => r.agent_id === agent.id,
    );

    const totalRuns = agentRuns.length;
    const successfulRuns = agentRuns.filter(
      (r: (typeof runRows)[0]) => r.status === "success",
    ).length;
    const completedRuns = agentRuns.filter(
      (r: (typeof runRows)[0]) => r.status !== "running",
    ).length;
    const successRate =
      completedRuns > 0
        ? Math.round((successfulRuns / completedRuns) * 100)
        : 0;
    const lastRun = agentRuns[0] ?? null;
    const lastVersion = agentVersions[0]?.version ?? "—";
    const status: Agent["status"] =
      lastRun?.status === "failed" ? "failed" : "active";

    const recentRuns: AgentRun[] = agentRuns
      .slice(0, 10)
      .map((r: (typeof runRows)[0]) => {
        const start = r.start_time.getTime();
        const end = r.end_time ? r.end_time.getTime() : start;
        const durationS = Math.max(0, Math.round((end - start) / 1000));
        return {
          id: r.id,
          status: r.status as AgentRun["status"],
          startTime: r.start_time.toISOString(),
          durationS,
          triggerType: r.trigger_type,
          triggerId: r.trigger_id,
          parentRunId: r.parent_run_id,
          spawnedRunCount: r._count.spawned_runs,
        };
      });

    return {
      id: agent.id,
      name: agent.name,
      owner: agent.owner,
      description: agent.description ?? "",
      runtime: agent.runtime ?? "—",
      tags: [],
      status,
      currentVersion: lastVersion,
      successRate,
      totalRuns,
      lastRunAt: lastRun?.start_time.toISOString() ?? null,
      versions: agentVersions.map((v: (typeof versionRows)[0]) => ({
        version: v.version,
        changelog: v.changelog ?? "",
        createdAt: v.created_at.toISOString(),
      })),
      recentRuns,
    };
  });
}

export type SpawnedRun = {
  id: string;
  status: string;
  startTime: string;
  durationS: number | null;
};

export async function listSpawnedRuns(parentRunId: string): Promise<SpawnedRun[]> {
  const runs = await prisma.agentRun.findMany({
    where: { parent_run_id: parentRunId },
    select: {
      id: true,
      status: true,
      start_time: true,
      end_time: true,
    },
    orderBy: { start_time: "asc" },
  });

  return runs.map((run: (typeof runs)[0]) => {
    const start = run.start_time.getTime();
    const end = run.end_time ? run.end_time.getTime() : null;
    const durationS = end !== null ? Math.max(0, Math.round((end - start) / 1000)) : null;
    return {
      id: run.id,
      status: run.status,
      startTime: run.start_time.toISOString(),
      durationS,
    };
  });
}
