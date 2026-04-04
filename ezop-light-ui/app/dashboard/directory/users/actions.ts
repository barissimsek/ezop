"use server"

import { prisma } from "@/lib/prisma"
import { getOrgContext } from "@/lib/db/getOrgContext"
import { revalidatePath } from "next/cache"

export async function removeUser(targetUserId: string): Promise<{ error?: string }> {
  const { organizationId, userId } = await getOrgContext()

  const caller = await prisma.organizationMember.findFirst({
    where:  { organization_id: organizationId, user_id: userId },
    select: { role: true },
  })

  if (caller?.role !== "owner") return { error: "Only the owner can remove users." }

  await prisma.organizationMember.deleteMany({
    where: {
      organization_id: organizationId,
      user_id:         targetUserId,
      role:            { not: "owner" },
    },
  })

  revalidatePath("/dashboard/directory/users")
  return {}
}

export type ImportResult = {
  imported: string[]
  skipped: { email: string; reason: string }[]
  error?: string
}

export async function importUsers(emails: string[]): Promise<ImportResult> {
  const { organizationId, userId } = await getOrgContext()

  const membership = await prisma.organizationMember.findFirst({
    where:  { organization_id: organizationId, user_id: userId },
    select: { role: true },
  })

  if (membership?.role !== "owner") {
    return { imported: [], skipped: [], error: "Only the organization owner can import users." }
  }

  // Get plan limits
  const org = await prisma.organization.findUnique({
    where:  { id: organizationId },
    select: { plan: true },
  })

  const planRow = await prisma.plan.findUnique({
    where:  { name: org?.plan ?? "free" },
    select: { limits: true },
  })

  const limits = planRow?.limits as { users?: number } | null
  const userLimit = limits?.users ?? 3

  const currentCount = await prisma.organizationMember.count({
    where: { organization_id: organizationId },
  })

  const availableSeats = userLimit - currentCount

  if (availableSeats <= 0) {
    return { imported: [], skipped: [], error: `No seats available. Your plan allows ${userLimit} users.` }
  }

  const toImport   = emails.slice(0, availableSeats)
  const overLimit  = emails.slice(availableSeats)

  const imported: string[] = []
  const skipped: { email: string; reason: string }[] = overLimit.map(e => ({
    email: e,
    reason: "Seat limit reached",
  }))

  for (const email of toImport) {
    // Check already a member
    const alreadyMember = await prisma.user.findFirst({
      where: {
        email,
        memberships: { some: { organization_id: organizationId } },
      },
      select: { id: true },
    })

    if (alreadyMember) {
      skipped.push({ email, reason: "Already a member" })
      continue
    }

    // Upsert user (may already exist in another org)
    let existingUser = await prisma.user.findUnique({
      where:  { email },
      select: { id: true },
    })

    if (!existingUser) {
      try {
        existingUser = await prisma.user.create({
          data:   { id: crypto.randomUUID(), email, firstname: null, lastname: null },
          select: { id: true },
        })
      } catch (err) {
        skipped.push({ email, reason: err instanceof Error ? err.message : "Failed to create user" })
        continue
      }
    }

    try {
      await prisma.organizationMember.create({
        data: { user_id: existingUser.id, organization_id: organizationId, role: "member" },
      })
      imported.push(email)
    } catch (err) {
      skipped.push({ email, reason: err instanceof Error ? err.message : "Failed to add member" })
    }
  }

  revalidatePath("/dashboard/directory/users")
  return { imported, skipped }
}
