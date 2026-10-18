"use client"

import { useState, useMemo } from "react"
import {
  ReactFlow, Background, Controls,
  Node, Edge, Position,
  Handle,
  useNodesState, useEdgesState,
} from "@xyflow/react"
import "@xyflow/react/dist/style.css"

// ─── Custom node ──────────────────────────────────────────────────────────────

type TraceNodeData = {
  label: string
  stat?: string
  sub?: string
  variant: "default" | "error" | "success" | "warning" | "muted"
  dimmed?: boolean
}

const VARIANT_STYLE: Record<TraceNodeData["variant"], { border: string; bg: string; color: string }> = {
  default: { border: "var(--accent)",  bg: "var(--sidebar-active-bg)",  color: "var(--accent)"  },
  success: { border: "#10B981",        bg: "rgba(16,185,129,0.12)",      color: "#10B981"        },
  error:   { border: "#EF4444",        bg: "rgba(239,68,68,0.12)",       color: "#EF4444"        },
  warning: { border: "#F59E0B",        bg: "rgba(245,158,11,0.12)",      color: "#F59E0B"        },
  muted:   { border: "#6B7280",        bg: "rgba(107,114,128,0.10)",     color: "#6B7280"        },
}

function TraceNode({ data }: { data: TraceNodeData }) {
  const s = VARIANT_STYLE[data.variant]
  return (
    <div style={{
      padding: "10px 16px", borderRadius: 10,
      border: `1.5px solid ${s.border}`, background: s.bg,
      minWidth: 148, textAlign: "center", backdropFilter: "blur(4px)",
      opacity: data.dimmed ? 0.25 : 1,
      transition: "opacity 0.2s",
    }}>
      <Handle type="target" position={Position.Top}    style={{ background: s.border, border: "none", width: 8, height: 8 }} />
      <Handle type="source" position={Position.Bottom} style={{ background: s.border, border: "none", width: 8, height: 8 }} />
      <Handle type="source" position={Position.Right}  id="r" style={{ background: s.border, border: "none", width: 8, height: 8 }} />
      <Handle type="target" position={Position.Left}   id="l" style={{ background: s.border, border: "none", width: 8, height: 8 }} />
      <div style={{ fontWeight: 600, fontSize: 13, color: s.color }}>{data.label}</div>
      {data.stat && <div style={{ fontSize: 12, color: "var(--main-text)", marginTop: 3, fontVariantNumeric: "tabular-nums" }}>{data.stat}</div>}
      {data.sub  && <div style={{ fontSize: 10, opacity: 0.6, marginTop: 2, color: "var(--main-text)" }}>{data.sub}</div>}
    </div>
  )
}

const nodeTypes = { trace: TraceNode }

// ─── Fixed node definitions ───────────────────────────────────────────────────

const TERMINALS = new Set(["success", "partial", "failed"])

type NodeDef = {
  label: string
  variant: TraceNodeData["variant"]
  x: number
  y: number
  sub?: string
}

const NODE_DEFS: Record<string, NodeDef> = {
  task_start: { label: "Task Start",  variant: "default", x: 210, y: 0,   sub: "entry point"         },
  reasoning:  { label: "Reasoning",   variant: "default", x: 210, y: 110, sub: "llm planning phase"   },
  tool_call:  { label: "Tool Call",   variant: "default", x: 80,  y: 230, sub: "tool invocation"      },
  tool_error: { label: "Tool Error",  variant: "error",   x: 360, y: 340, sub: "api / timeout / 429"  },
  retry:      { label: "Retry",       variant: "warning", x: 360, y: 450, sub: "backoff + re-invoke"  },
  validation: { label: "Validation",  variant: "default", x: 210, y: 450, sub: "output check"         },
  success:    { label: "✓ Success",   variant: "success", x: 60,  y: 560                              },
  partial:    { label: "⚠ Partial",   variant: "warning", x: 230, y: 560                              },
  failed:     { label: "✗ Failed",    variant: "error",   x: 400, y: 560                              },
}

// ─── Common path computation ──────────────────────────────────────────────────

function computeFailurePaths(
  edgeCounts: Record<string, number>,
  availableNodeIds: Set<string>,
): { pathNodes: Set<string>; pathEdgeKeys: Set<string> } {
  const pathNodes    = new Set<string>()
  const pathEdgeKeys = new Set<string>()

  // Reverse traversal: start from failure terminals, walk backwards
  const FAILURE_TERMINALS = new Set(["failed", "partial"])
  const queue = [...FAILURE_TERMINALS].filter(n => availableNodeIds.has(n))
  const visited = new Set<string>()

  for (const t of queue) pathNodes.add(t)

  while (queue.length > 0) {
    const current = queue.shift()!
    if (visited.has(current)) continue
    visited.add(current)

    for (const [key] of Object.entries(edgeCounts)) {
      const [from, to] = key.split("→")
      if (to === current && availableNodeIds.has(from) && !visited.has(from)) {
        pathNodes.add(from)
        pathEdgeKeys.add(key)
        queue.push(from)
      }
    }
  }

  return { pathNodes, pathEdgeKeys }
}

function computeCommonPath(
  edgeCounts: Record<string, number>,
  availableNodeIds: Set<string>,
): { pathNodes: Set<string>; pathEdgeKeys: Set<string> } {
  const pathNodes    = new Set<string>()
  const pathEdgeKeys = new Set<string>()

  let current = "task_start"
  const visited = new Set<string>()

  while (!TERMINALS.has(current) && !visited.has(current)) {
    pathNodes.add(current)
    visited.add(current)

    // Find best outgoing edge from current
    let bestKey   = ""
    let bestCount = -1

    for (const [key, count] of Object.entries(edgeCounts)) {
      const [from, to] = key.split("→")
      if (from === current && availableNodeIds.has(to) && count > bestCount) {
        bestCount = count
        bestKey   = key
      }
    }

    if (!bestKey) break

    const [, next] = bestKey.split("→")
    pathEdgeKeys.add(bestKey)
    current = next
  }

  pathNodes.add(current) // terminal
  return { pathNodes, pathEdgeKeys }
}

// ─── Props ────────────────────────────────────────────────────────────────────

type Props = {
  nodeCounts: Record<string, number>
  edgeCounts: Record<string, number>
  totalRuns:  number
}

// ─── Toggle button ────────────────────────────────────────────────────────────

function Toggle({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      style={{
        display: "flex", alignItems: "center", gap: "0.4rem",
        padding: "0.35rem 0.75rem", borderRadius: 6, fontSize: 12, fontWeight: 500,
        border: `1px solid ${active ? "var(--accent)" : "var(--card-border)"}`,
        background: active ? "var(--sidebar-active-bg)" : "var(--card-bg)",
        color: active ? "var(--accent)" : "var(--text-muted)",
        cursor: "pointer", transition: "all 0.15s",
      }}
    >
      <span style={{
        width: 12, height: 12, borderRadius: 3, flexShrink: 0,
        border: `1.5px solid ${active ? "var(--accent)" : "var(--card-border)"}`,
        background: active ? "var(--accent)" : "transparent",
        display: "flex", alignItems: "center", justifyContent: "center",
      }}>
        {active && <span style={{ color: "#fff", fontSize: 9, lineHeight: 1, fontWeight: 700 }}>✓</span>}
      </span>
      {children}
    </button>
  )
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function DecisionTraceMap({ nodeCounts, edgeCounts, totalRuns }: Props) {
  const [showAll,          setShowAll]          = useState(false)
  const [highlightTop,     setHighlightTop]     = useState(false)
  const [highlightFailure, setHighlightFailure] = useState(false)
  const hasData = totalRuns > 0

  // Roll up tool_call:xxx and tool_error:xxx into canonical node counts
  const rolledUp = useMemo(() => {
    const result: Record<string, number> = { ...nodeCounts }
    for (const [key, count] of Object.entries(nodeCounts)) {
      const canonical = key.split(":")[0]
      if (canonical !== key && NODE_DEFS[canonical]) {
        result[canonical] = (result[canonical] ?? 0) + count
        delete result[key]
      }
    }
    return result
  }, [nodeCounts])

  const rolledEdges = useMemo(() => {
    const result: Record<string, number> = {}
    for (const [key, count] of Object.entries(edgeCounts)) {
      const [from, to] = key.split("→")
      const cf = from.split(":")[0]
      const ct = to.split(":")[0]
      const canonical = `${NODE_DEFS[cf] ? cf : from}→${NODE_DEFS[ct] ? ct : to}`
      result[canonical] = (result[canonical] ?? 0) + count
    }
    return result
  }, [edgeCounts])

  // Build base node list
  const baseNodes: Node[] = useMemo(() => Object.entries(NODE_DEFS)
    .filter(([id]) => showAll || !hasData || (rolledUp[id] ?? 0) > 0)
    .map(([id, def]) => {
      const count = rolledUp[id] ?? 0
      const pct   = totalRuns > 0 ? Math.round((count / totalRuns) * 100) : 0
      const stat  = hasData
        ? `${count.toLocaleString()} run${count !== 1 ? "s" : ""} (${pct}%)`
        : undefined
      return {
        id,
        type: "trace",
        position: { x: def.x, y: def.y },
        data: { label: def.label, stat, sub: hasData ? undefined : def.sub, variant: def.variant } satisfies TraceNodeData,
      }
    }), [showAll, hasData, rolledUp, totalRuns])

  const nodeIds = useMemo(() => new Set(baseNodes.map(n => n.id)), [baseNodes])

  // Compute highlighted path (common or failure — mutually exclusive, last toggled wins)
  const { pathNodes, pathEdgeKeys } = useMemo(() => {
    if (hasData && highlightFailure) return computeFailurePaths(rolledEdges, nodeIds)
    if (hasData && highlightTop)     return computeCommonPath(rolledEdges, nodeIds)
    return { pathNodes: new Set<string>(), pathEdgeKeys: new Set<string>() }
  }, [highlightTop, highlightFailure, hasData, rolledEdges, nodeIds])

  // Apply dimming to nodes
  const finalNodes: Node[] = useMemo(() => baseNodes.map(n => ({
    ...n,
    data: {
      ...n.data,
      dimmed: highlightTop && pathNodes.size > 0 && !pathNodes.has(n.id),
    },
  })), [baseNodes, highlightTop, pathNodes])

  function edgeColor(to: string): string {
    if (to === "success")    return "#10B981"
    if (to === "failed")     return "#EF4444"
    if (to === "partial")    return "#F59E0B"
    if (to === "tool_error") return "#EF4444"
    if (to === "retry")      return "#F59E0B"
    return "var(--accent)"
  }

  const maxEdge = Math.max(...Object.values(rolledEdges), 1)

  const allEdges: Edge[] = useMemo(() => Object.entries(rolledEdges)
    .filter(([key]) => {
      const [from, to] = key.split("→")
      return nodeIds.has(from) && nodeIds.has(to)
    })
    .map(([key, count], i) => {
      const [from, to] = key.split("→")
      const fromCount  = rolledUp[from] ?? 1
      const pct        = Math.round((count / fromCount) * 100)
      const isOnPath   = pathEdgeKeys.has(key)
      const dimmed     = highlightTop && pathEdgeKeys.size > 0 && !isOnPath
      const color      = dimmed ? "#6B728033" : edgeColor(to)
      const strokeW    = isOnPath ? 3.5 : 0.8 + (count / maxEdge) * 3.5
      return {
        id:    `e${i}`,
        source: from,
        target: to,
        label:  `${pct}%`,
        type:  "smoothstep",
        animated: isOnPath,
        style: { stroke: color, strokeWidth: strokeW, transition: "stroke 0.2s, stroke-width 0.2s" },
        labelStyle: { fontSize: 10, fill: dimmed ? "transparent" : edgeColor(to), fontWeight: 600 },
        labelBgStyle: { fill: "var(--card-bg)", fillOpacity: dimmed ? 0 : 0.9 },
        labelBgPadding: [4, 6] as [number, number],
        labelBgBorderRadius: 4,
      }
    }), [rolledEdges, nodeIds, rolledUp, highlightTop, pathEdgeKeys, maxEdge])

  const [nodes, setNodes, onNodesChange] = useNodesState(finalNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(allEdges)

  // Sync derived state changes into ReactFlow
  useMemo(() => setNodes(finalNodes), [finalNodes])
  useMemo(() => setEdges(allEdges),   [allEdges])

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {/* Toggles */}
      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
        <Toggle active={showAll} onClick={() => setShowAll(v => !v)}>
          Show all paths
        </Toggle>
        <Toggle active={highlightTop} onClick={() => { setHighlightTop(v => !v); setHighlightFailure(false) }}>
          Highlight most common path
        </Toggle>
        <Toggle active={highlightFailure} onClick={() => { setHighlightFailure(v => !v); setHighlightTop(false) }}>
          Highlight failure paths
        </Toggle>
      </div>

      {/* Graph */}
      <div style={{ height: 560, borderRadius: 8, overflow: "hidden", border: "1px solid var(--card-border)", background: "var(--main-bg)", position: "relative" }}>
        {!hasData && (
          <div style={{
            position: "absolute", inset: 0, zIndex: 10,
            display: "flex", alignItems: "center", justifyContent: "center",
            color: "var(--text-muted)", fontSize: 13,
            background: "var(--main-bg)",
          }}>
            No completed runs in the last 30 days.
          </div>
        )}
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.25 }}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          panOnDrag={true}
          zoomOnScroll={false}
          minZoom={0.4}
          maxZoom={1.5}
          proOptions={{ hideAttribution: true }}
          style={{ background: "var(--main-bg)" }}
        >
          <Background gap={20} size={1} color="var(--chart-grid)" />
          <Controls showInteractive={false} style={{ bottom: 12, right: 12, left: "auto" }} />
        </ReactFlow>
      </div>
    </div>
  )
}
