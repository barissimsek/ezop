import { auth, signOut } from "@/auth";
import ThemeToggle from "@/components/ThemeToggle";
import Image from "next/image";
import UserMenuWrapper from "@/components/UserMenuWrapper";

const navItem = (href: string, label: string) => ({ href, label });
const subItem = (href: string, label: string) => ({ href, label });

const NAV = [
  {
    ...navItem("/dashboard", "Home"),
    children: [],
  },
  {
    href: null,
    label: "Agents",
    children: [subItem("/dashboard/agents", "Inventory")],
  },
  {
    href: null,
    label: "Observability",
    children: [
      subItem("/dashboard/agent-performance", "Agent Performance"),
      subItem("/dashboard/agent-reasoning", "Agent Reasoning"),
      subItem("/dashboard/observability/events", "Events"),
    ],
  },
  {
    href: null,
    label: "Directory",
    children: [
      subItem("/dashboard/directory/users", "Users"),
      subItem("/dashboard/directory/organization", "Organization"),
    ],
  },
  {
    href: null,
    label: "Security",
    children: [
      subItem("/dashboard/api-keys", "API Keys"),
      subItem("/dashboard/audit-log", "Audit Logs"),
      subItem("/dashboard/security/danger-zone", "Danger Zone"),
    ],
  },
];

export default async function Sidebar() {
  const session = await auth();

  return (
    <aside
      style={{
        width: "240px",
        minHeight: "100vh",
        background: "var(--sidebar-bg)",
        color: "var(--sidebar-text)",
        display: "flex",
        flexDirection: "column",
        padding: "1.5rem 1rem",
        flexShrink: 0,
        borderRight: "1px solid var(--sidebar-border)",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0.5rem",
          fontSize: "1.25rem",
          fontWeight: 700,
          marginBottom: "2rem",
          paddingLeft: "0.5rem",
          color: "var(--sidebar-text)",
          letterSpacing: "-0.01em",
        }}
      >
        <Image src="/icon.svg" alt="Ezop logo" width={24} height={24} />
        Ezop
      </div>

      <nav
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          gap: "0.125rem",
        }}
      >
        {NAV.map((item) => (
          <div key={item.label}>
            {item.href ? (
              <a
                href={item.href}
                style={{
                  display: "block",
                  padding: "0.6rem 0.75rem",
                  borderRadius: "6px",
                  color: "var(--sidebar-text)",
                  background: "var(--sidebar-active-bg)",
                  fontWeight: 500,
                  fontSize: "0.9rem",
                }}
              >
                {item.label}
              </a>
            ) : (
              <div
                style={{
                  padding: "0.4rem 0.75rem 0.2rem",
                  fontSize: "0.7rem",
                  fontWeight: 600,
                  letterSpacing: "0.08em",
                  textTransform: "uppercase",
                  color: "var(--sidebar-text-muted)",
                  marginTop: "0.75rem",
                }}
              >
                {item.label}
              </div>
            )}

            {item.children && (
              <div
                style={{
                  paddingLeft: "0.75rem",
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.125rem",
                  marginTop: "0.125rem",
                }}
              >
                {item.children.map((child) => (
                  <a
                    key={child.href}
                    href={child.href}
                    style={{
                      display: "block",
                      padding: "0.45rem 0.75rem",
                      borderRadius: "6px",
                      color: "var(--sidebar-text)",
                      fontSize: "0.85rem",
                      borderLeft: "2px solid var(--sidebar-border)",
                    }}
                  >
                    {child.label}
                  </a>
                ))}
              </div>
            )}
          </div>
        ))}
      </nav>

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "0.5rem",
          borderTop: "1px solid var(--sidebar-border)",
          paddingTop: "1rem",
        }}
      >
        <ThemeToggle />
        <UserMenuWrapper
          name={session?.user?.name}
          signOutAction={async () => {
            "use server";
            await signOut({ redirectTo: "https://accounts.google.com/logout" });
          }}
        />
      </div>
    </aside>
  );
}
