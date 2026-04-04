import { auth } from "@/auth"
import { redirect } from "next/navigation"
import OnboardingForm from "./OnboardingForm"

export default async function OnboardingPage() {
  const session = await auth()
  if (!session?.user?.email) redirect("/")

  // Parse first/last from Google display name
  const fullName  = session.user.name ?? ""
  const parts     = fullName.trim().split(" ")
  const firstName = parts[0] ?? ""
  const lastName  = parts.slice(1).join(" ")

  return (
    <main style={{
      minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center",
      background: "var(--main-bg)", padding: "2rem",
    }}>
      <div style={{
        width: "100%", maxWidth: 480,
        background: "var(--card-bg)", border: "1px solid var(--card-border)",
        borderRadius: 16, padding: "2rem",
        boxShadow: "0 4px 32px rgba(0,0,0,0.12)",
      }}>
        <div style={{ marginBottom: "2rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: "1rem" }}>
            <div style={{ width: 32, height: 32, borderRadius: 8, background: "var(--accent)", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <span style={{ color: "#fff", fontSize: 16, fontWeight: 700 }}>E</span>
            </div>
            <span style={{ fontWeight: 700, fontSize: 18, color: "var(--main-text)" }}>Ezop</span>
          </div>
          <h1 style={{ fontSize: "1.4rem", fontWeight: 700, color: "var(--main-text)", margin: 0 }}>
            Welcome! Let's set up your workspace
          </h1>
          <p style={{ marginTop: 8, fontSize: 14, color: "var(--text-muted)", lineHeight: 1.5 }}>
            Confirm your details and name your organization to get started.
          </p>
        </div>

        <OnboardingForm
          email={session.user.email}
          firstName={firstName}
          lastName={lastName}
        />
      </div>
    </main>
  )
}
