"use server";

import { createHash, randomBytes } from "crypto";

import { prisma } from "@/lib/prisma";
import type { audit_action_t } from "@prisma/client";
import { getOrgContext } from "@/lib/db/getOrgContext";
import { revalidatePath } from "next/cache";

export type ApiKey = {
  id: string;
  name: string;
  description: string | null;
  key_prefix: string;
  scopes: string[];
  last_used_at: string | null;
  expires_at: string | null;
  revoked_at: string | null;
  created_at: string;
};

function generateKey(): { raw: string; prefix: string; hash: string } {
  const secret = randomBytes(32).toString("hex");
  const raw = `ezop_sk_${secret}`;
  const prefix = `ezop_sk_${secret.slice(0, 8)}`;
  const hash = createHash("sha256").update(raw).digest("hex");
  return { raw, prefix, hash };
}

async function insertAuditLog({
  organizationId,
  actorId,
  action,
  resourceId,
  metadata,
}: {
  organizationId: string;
  actorId: string;
  action: audit_action_t;
  resourceId?: string | null;
  metadata?: Record<string, unknown>;
}) {
  await prisma.auditLog.create({
    data: {
      organization_id: organizationId,
      actor_type: "user",
      actor_id: actorId,
      action,
      resource_type: "apikey",
      resource_id: resourceId ?? null,
      metadata: (metadata ?? {}) as any,
    },
  });
}

function toApiKey(row: {
  id: string;
  name: string;
  description: string | null;
  key_prefix: string;
  scopes: string[];
  last_used_at: Date | null;
  expires_at: Date | null;
  revoked_at: Date | null;
  created_at: Date;
}): ApiKey {
  return {
    id: row.id,
    name: row.name,
    description: row.description,
    key_prefix: row.key_prefix,
    scopes: row.scopes,
    last_used_at: row.last_used_at?.toISOString() ?? null,
    expires_at: row.expires_at?.toISOString() ?? null,
    revoked_at: row.revoked_at?.toISOString() ?? null,
    created_at: row.created_at.toISOString(),
  };
}

export async function listApiKeys(): Promise<ApiKey[]> {
  const { organizationId } = await getOrgContext();

  const rows = await prisma.apiKey.findMany({
    where: { organization_id: organizationId },
    orderBy: { created_at: "desc" },
    select: {
      id: true,
      name: true,
      description: true,
      key_prefix: true,
      scopes: true,
      last_used_at: true,
      expires_at: true,
      revoked_at: true,
      created_at: true,
    },
  });

  return rows.map(toApiKey);
}

/** Returns the raw key — only available at creation time */
export async function createApiKey(
  name: string,
  description: string,
  scopes: string[],
  expiresInDays: number | null,
): Promise<{ key: ApiKey; rawKey: string }> {
  const { userId, organizationId } = await getOrgContext();
  const { raw, prefix, hash } = generateKey();

  const expires_at = expiresInDays
    ? new Date(Date.now() + expiresInDays * 86400000)
    : null;

  const org = await prisma.organization.findUnique({
    where: { id: organizationId },
    select: { plan: true },
  });

  const key = await prisma.apiKey.create({
    data: {
      name,
      description: description || null,
      key_prefix: prefix,
      key_hash: hash,
      scopes,
      organization_id: organizationId,
      created_by: userId,
      expires_at,
      plan: org?.plan ?? null,
    },
    select: {
      id: true,
      name: true,
      description: true,
      key_prefix: true,
      scopes: true,
      last_used_at: true,
      expires_at: true,
      revoked_at: true,
      created_at: true,
    },
  });

  await insertAuditLog({
    organizationId,
    actorId: userId,
    action: "apikey_created",
    resourceId: key.id,
    metadata: {
      target: prefix,
      description: `Created API key "${name}"`,
      name,
      scopes,
      expires_at: expires_at?.toISOString() ?? null,
    },
  });

  revalidatePath("/dashboard/api-keys");
  return { key: toApiKey(key), rawKey: raw };
}

export async function revokeApiKey(id: string): Promise<void> {
  const { userId, organizationId } = await getOrgContext();

  const existing = await prisma.apiKey.findFirst({
    where: { id, organization_id: organizationId },
    select: { name: true, key_prefix: true },
  });

  await prisma.apiKey.updateMany({
    where: { id, organization_id: organizationId },
    data: { revoked_at: new Date() },
  });

  await insertAuditLog({
    organizationId,
    actorId: userId,
    action: "apikey_updated",
    resourceId: id,
    metadata: {
      target: existing?.key_prefix ?? id,
      description: `Revoked API key "${existing?.name ?? id}"`,
      change: "revoked",
    },
  });

  revalidatePath("/dashboard/api-keys");
}

export async function deleteApiKey(id: string): Promise<void> {
  const { userId, organizationId } = await getOrgContext();

  const existing = await prisma.apiKey.findFirst({
    where: { id, organization_id: organizationId },
    select: { name: true, key_prefix: true },
  });

  // Safety: only delete already-revoked keys
  await prisma.apiKey.deleteMany({
    where: { id, organization_id: organizationId, revoked_at: { not: null } },
  });

  await insertAuditLog({
    organizationId,
    actorId: userId,
    action: "apikey_deleted",
    resourceId: id,
    metadata: {
      target: existing?.key_prefix ?? id,
      description: `Deleted API key "${existing?.name ?? id}"`,
    },
  });

  revalidatePath("/dashboard/api-keys");
}

/** Revokes the old key and creates a replacement with the same name/scopes */
export async function rotateApiKey(id: string): Promise<{ rawKey: string }> {
  const { userId, organizationId } = await getOrgContext();

  const old = await prisma.apiKey.findFirst({
    where: { id, organization_id: organizationId },
    select: {
      name: true,
      description: true,
      scopes: true,
      expires_at: true,
      key_prefix: true,
    },
  });

  if (!old) throw new Error("Key not found");

  const { raw, prefix, hash } = generateKey();

  const [, newKey] = await prisma.$transaction([
    prisma.apiKey.update({
      where: { id },
      data: { revoked_at: new Date() },
    }),
    prisma.apiKey.create({
      data: {
        name: old.name,
        description: old.description,
        key_prefix: prefix,
        key_hash: hash,
        scopes: old.scopes,
        organization_id: organizationId,
        created_by: userId,
        expires_at: old.expires_at,
      },
      select: { id: true },
    }),
  ]);

  await insertAuditLog({
    organizationId,
    actorId: userId,
    action: "apikey_updated",
    resourceId: newKey.id,
    metadata: {
      target: old.key_prefix,
      description: `Rotated API key "${old.name}"`,
      change: "rotated",
      old_prefix: old.key_prefix,
      new_prefix: prefix,
    },
  });

  revalidatePath("/dashboard/api-keys");
  return { rawKey: raw };
}
