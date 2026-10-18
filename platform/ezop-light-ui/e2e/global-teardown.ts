import { test as teardown } from "@playwright/test";
import { prisma } from "../lib/prisma";
import { TEST_USER_ID, TEST_ORG_ID, TEST_AGENT_ID } from "./constants";
import dotenv from "dotenv";
dotenv.config({ path: ".env.local" });
dotenv.config();

teardown("remove test data", async () => {
  await prisma.agentRun.deleteMany({ where: { agent_id: TEST_AGENT_ID } });
  await prisma.agent.deleteMany({ where: { id: TEST_AGENT_ID } });
  await prisma.apiKey.deleteMany({ where: { organization_id: TEST_ORG_ID } });
  await prisma.auditLog.deleteMany({ where: { organization_id: TEST_ORG_ID } });
  await prisma.organizationMember.deleteMany({
    where: { user_id: TEST_USER_ID },
  });
  await prisma.organization.deleteMany({ where: { id: TEST_ORG_ID } });
  await prisma.user.deleteMany({ where: { id: TEST_USER_ID } });
  await prisma.$disconnect();
});
