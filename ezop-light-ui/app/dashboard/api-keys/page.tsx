import { listApiKeys } from "./actions"
import ApiKeyManager from "@/components/ApiKeyManager"

export default async function ApiKeysPage() {
  const keys = await listApiKeys()

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <div>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 700 }}>API Keys</h1>
        <p style={{ color: "var(--text-muted)", marginTop: "0.25rem", fontSize: "0.9rem" }}>
          Manage keys that allow external systems to interact with Ezop. Raw keys are never stored.
        </p>
      </div>

      <ApiKeyManager initialKeys={keys} />
    </div>
  )
}
