import { auth } from "@/auth"
import { prisma } from "@/lib/prisma"

export async function getOrgContext(): Promise<{ userId: string; organizationId: string }> {
  const session = await auth()
  if (!session?.user?.email) throw new Error("Not authenticated")

  const user = await prisma.user.findUnique({
    where: { email: session.user.email },
    select: { id: true, memberships: { select: { organization_id: true }, take: 1 } },
  })

  if (!user) throw new Error("User not found — complete onboarding first")

  const membership = user.memberships[0]
  if (!membership) throw new Error("No organization found for this user")

  return { userId: user.id, organizationId: membership.organization_id }
}
