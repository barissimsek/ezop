import { listAgents } from "./actions"
import AgentInventory from "@/components/AgentInventory"

export default async function AgentsPage() {
  const agents = await listAgents()

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <div>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 700 }}>Agent Inventory</h1>
        <p style={{ color: "var(--text-muted)", marginTop: "0.25rem", fontSize: "0.9rem" }}>
          Every agent your team has deployed, observed in one place.
        </p>
      </div>
      <AgentInventory initialAgents={agents} />
    </div>
  )
}
