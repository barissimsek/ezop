"use client"

const runs = [
  { agent: "ResearchBot",    runTime: 92, steps: 27, cost: 1.40, status: "partial" },
  { agent: "DataPipeline",   runTime: 78, steps: 41, cost: 2.10, status: "error"   },
  { agent: "ReportGen",      runTime: 61, steps: 19, cost: 0.98, status: "success" },
  { agent: "WebScraper",     runTime: 54, steps: 33, cost: 1.22, status: "error"   },
  { agent: "AlertAgent",     runTime: 47, steps: 12, cost: 0.61, status: "success" },
  { agent: "EmailBot",       runTime: 38, steps: 9,  cost: 0.44, status: "partial" },
]

const MAX_TIME = runs[0].runTime

const STATUS_COLOR: Record<string, string> = {
  success: "#10B981",
  error:   "#EF4444",
  partial: "#F59E0B",
}

export default function SlowestRunsTable() {
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.875rem" }}>
        <thead>
          <tr style={{ borderBottom: "1px solid var(--card-border)" }}>
            {["Agent", "Run Time", "Steps", "Cost", "Status"].map((h) => (
              <th key={h} style={{
                textAlign: h === "Steps" || h === "Cost" || h === "Status" ? "center" : "left",
                padding: "0 0.75rem 0.75rem",
                color: "var(--text-muted)",
                fontWeight: 500,
                fontSize: "0.75rem",
                textTransform: "uppercase",
                letterSpacing: "0.05em",
                whiteSpace: "nowrap",
              }}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {runs.map((run, i) => (
            <tr key={run.agent} style={{ borderBottom: i < runs.length - 1 ? "1px solid var(--card-border)" : "none" }}>
              {/* Agent */}
              <td style={{ padding: "0.75rem", fontFamily: "monospace", color: "var(--main-text)", whiteSpace: "nowrap" }}>
                {run.agent}
              </td>

              {/* Run Time + bar */}
              <td style={{ padding: "0.75rem", minWidth: 180 }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
                  <div style={{ flex: 1, height: 6, background: "var(--card-border)", borderRadius: 3, overflow: "hidden" }}>
                    <div style={{
                      height: "100%",
                      width: `${(run.runTime / MAX_TIME) * 100}%`,
                      background: run.runTime > 70 ? "#EF4444" : run.runTime > 50 ? "#F59E0B" : "#10B981",
                      borderRadius: 3,
                    }} />
                  </div>
                  <span style={{ color: "var(--main-text)", fontVariantNumeric: "tabular-nums", minWidth: 32, textAlign: "right" }}>
                    {run.runTime}s
                  </span>
                </div>
              </td>

              {/* Steps */}
              <td style={{ padding: "0.75rem", textAlign: "center", color: "var(--text-muted)", fontVariantNumeric: "tabular-nums" }}>
                {run.steps}
              </td>

              {/* Cost */}
              <td style={{ padding: "0.75rem", textAlign: "center", color: "var(--main-text)", fontVariantNumeric: "tabular-nums" }}>
                ${run.cost.toFixed(2)}
              </td>

              {/* Status */}
              <td style={{ padding: "0.75rem", textAlign: "center" }}>
                <span style={{
                  display: "inline-block",
                  padding: "2px 10px",
                  borderRadius: 99,
                  fontSize: "0.75rem",
                  fontWeight: 500,
                  background: STATUS_COLOR[run.status] + "22",
                  color: STATUS_COLOR[run.status],
                }}>
                  {run.status}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
