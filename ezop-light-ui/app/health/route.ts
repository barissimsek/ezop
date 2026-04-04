import { prisma } from "@/lib/prisma"

export const dynamic = "force-dynamic"

export async function GET() {
  const start = Date.now()

  let dbStatus: "healthy" | "unhealthy" = "unhealthy"
  let dbLatencyMs: number | null = null
  let dbError: string | null = null

  try {
    const dbStart = Date.now()
    await prisma.user.findFirst({ select: { id: true } })
    dbLatencyMs = Date.now() - dbStart
    dbStatus    = "healthy"
  } catch (err) {
    dbError = err instanceof Error ? err.message : "Unknown error"
  }

  const overall = dbStatus === "healthy" ? "healthy" : "degraded"

  return Response.json(
    {
      status:    overall,
      timestamp: new Date().toISOString(),
      latencyMs: Date.now() - start,
      components: {
        backend:  { status: "healthy" },
        database: { status: dbStatus, latencyMs: dbLatencyMs, ...(dbError ? { error: dbError } : {}) },
      },
    },
    { status: overall === "healthy" ? 200 : 503 }
  )
}
