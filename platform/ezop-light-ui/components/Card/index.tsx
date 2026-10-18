export default function Card({
  title,
  description,
  fullWidth,
  children,
}: {
  title: string
  description?: string
  fullWidth?: boolean
  children: React.ReactNode
}) {
  return (
    <div style={{
      background: "var(--card-bg)",
      borderRadius: "12px",
      padding: "1.5rem",
      border: "1px solid var(--card-border)",
      display: "flex",
      flexDirection: "column",
      gap: "1rem",
      gridColumn: fullWidth ? "1 / -1" : undefined,
    }}>
      <div>
        <h2 style={{ fontSize: "1rem", fontWeight: 600, color: "var(--main-text)" }}>{title}</h2>
        {description && (
          <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>{description}</p>
        )}
      </div>
      {children}
    </div>
  )
}
