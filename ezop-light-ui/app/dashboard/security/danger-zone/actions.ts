"use server";

import { prisma } from "@/lib/prisma";
import { getOrgContext } from "@/lib/db/getOrgContext";
import { signOut } from "@/auth";
import { redirect } from "next/navigation";

async function requireOwner() {
  const { organizationId, userId } = await getOrgContext();

  const membership = await prisma.organizationMember.findFirst({
    where: { organization_id: organizationId, user_id: userId },
    select: { role: true },
  });

  if (membership?.role !== "owner")
    throw new Error("Only the organization owner can perform this action.");

  return { organizationId, userId };
}

export async function deleteEvents(): Promise<void> {
  const { organizationId, userId } = await requireOwner();

  await prisma.$transaction([
    prisma.event.deleteMany({ where: { organization_id: organizationId } }),
    prisma.span.deleteMany({ where: { organization_id: organizationId } }),
    prisma.agentRun.deleteMany({ where: { organization_id: organizationId } }),
    prisma.auditLog.create({
      data: {
        organization_id: organizationId,
        actor_type: "user",
        actor_id: userId,
        action: "events_deleted",
        resource_type: "organization",
        resource_id: organizationId,
        metadata: {
          target: organizationId,
          description: "All events, spans and agent runs deleted by owner",
        },
      },
    }),
  ]);
}

export async function deleteAccount(): Promise<void> {
  const { organizationId, userId } = await requireOwner();

  // Cascade delete everything in the organization
  await prisma.$transaction([
    prisma.event.deleteMany({ where: { organization_id: organizationId } }),
    prisma.span.deleteMany({ where: { organization_id: organizationId } }),
    prisma.agentRun.deleteMany({ where: { organization_id: organizationId } }),
    prisma.agentVersion.deleteMany({
      where: { organization_id: organizationId },
    }),
    prisma.agent.deleteMany({ where: { organization_id: organizationId } }),
    prisma.apiKey.deleteMany({ where: { organization_id: organizationId } }),
    prisma.auditLog.deleteMany({ where: { organization_id: organizationId } }),
    prisma.organizationMember.deleteMany({
      where: { organization_id: organizationId },
    }),
    prisma.user.delete({ where: { id: userId } }),
    prisma.organization.delete({ where: { id: organizationId } }),
  ]);

  await signOut({ redirect: false });
  redirect("/");
}
