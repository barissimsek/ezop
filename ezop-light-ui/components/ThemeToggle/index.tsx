"use client"

import { useTheme } from "next-themes"
import { useEffect, useState } from "react"

export default function ThemeToggle() {
  const { theme, setTheme } = useTheme()
  const [mounted, setMounted] = useState(false)

  useEffect(() => setMounted(true), [])
  if (!mounted) return null

  const isDark = theme === "dark"

  return (
    <button
      onClick={() => setTheme(isDark ? "light" : "dark")}
      title={isDark ? "Switch to light mode" : "Switch to dark mode"}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "0.5rem",
        width: "100%",
        padding: "0.5rem 0.75rem",
        background: "transparent",
        border: "1px solid var(--sidebar-border)",
        borderRadius: "6px",
        color: "var(--sidebar-text)",
        cursor: "pointer",
        fontSize: "0.875rem",
        transition: "background 0.15s",
      }}
    >
      <span style={{ fontSize: "1rem" }}>{isDark ? "☀️" : "🌙"}</span>
      {isDark ? "Light mode" : "Dark mode"}
    </button>
  )
}
