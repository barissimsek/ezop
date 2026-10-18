import Sidebar from "@/components/Sidebar"
import { auth } from "@/auth"
import { prisma } from "@/lib/prisma"
import { redirect } from "next/navigation"

export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  const session = await auth()
  if (!session?.user?.email) redirect("/")

  const user = await prisma.user.findUnique({
    where: { email: session.user.email },
    select: {
      id: true,
      memberships: { select: { organization_id: true }, take: 1 },
    },
  })

  if (!user) redirect("/onboarding")

  return (
    <div style={{ display: "flex", minHeight: "100vh" }}>
      <Sidebar />
      <main style={{ flex: 1, padding: "2rem", background: "var(--main-bg)", color: "var(--main-text)", transition: "background 0.2s, color 0.2s" }}>
        {children}
      </main>
    </div>
  )
}
