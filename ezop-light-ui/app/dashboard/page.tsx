import { auth } from "@/auth"

export default async function HomePage() {
  const session = await auth()

  return (
    <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", height: "100%" }}>
      <h1 style={{ fontSize: "2rem", fontWeight: 700 }}>Welcome back, {session?.user?.name?.split(" ")[0]} 👋</h1>
      <p style={{ color: "var(--text-muted)", marginTop: "0.5rem", fontSize: "1rem" }}>
        Select a section from the sidebar to get started.
      </p>
    </div>
  )
}
