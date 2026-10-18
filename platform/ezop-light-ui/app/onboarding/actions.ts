"use server"

import { auth } from "@/auth"
import { prisma } from "@/lib/prisma"
import { redirect } from "next/navigation"

export async function completeOnboarding(formData: FormData) {
  const session = await auth()
  if (!session?.user?.email) throw new Error("Not authenticated")

  const firstName = (formData.get("firstName") as string)?.trim()
  const lastName  = (formData.get("lastName")  as string)?.trim()
  const orgName   = (formData.get("orgName")   as string)?.trim()

  if (!firstName || !lastName || !orgName) throw new Error("All fields are required")

  // Guard: don't double-create
  const existing = await prisma.user.findUnique({
    where:  { email: session.user.email },
    select: { id: true },
  })
  if (existing) redirect("/dashboard")

  const userId = crypto.randomUUID()

  const [, org] = await prisma.$transaction([
    prisma.user.create({
      data: { id: userId, email: session.user.email, firstname: firstName, lastname: lastName },
    }),
    prisma.organization.create({
      data: { name: orgName },
    }),
  ])

  await prisma.organizationMember.create({
    data: { user_id: userId, organization_id: org.id, role: "owner" },
  })

  redirect("/dashboard")
}
