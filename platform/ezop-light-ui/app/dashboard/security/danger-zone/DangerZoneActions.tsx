"use client";

import { useState, useTransition } from "react";
import { deleteEvents, deleteAccount } from "./actions";

function ConfirmModal({
  title,
  description,
  confirmLabel,
  confirmPhrase,
  onConfirm,
  onClose,
  isPending,
}: {
  title: string;
  description: string;
  confirmLabel: string;
  confirmPhrase: string;
  onConfirm: () => void;
  onClose: () => void;
  isPending: boolean;
}) {
  const [input, setInput] = useState("");
  const matches = input === confirmPhrase;

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.6)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "var(--card-bg)",
          border: "1px solid #EF444466",
          borderRadius: 14,
          padding: "1.75rem",
          width: 460,
          display: "flex",
          flexDirection: "column",
          gap: "1.25rem",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
          }}
        >
          <h2
            style={{
              margin: 0,
              fontSize: "1.1rem",
              fontWeight: 700,
              color: "#EF4444",
            }}
          >
            {title}
          </h2>
          <button
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              color: "var(--text-muted)",
              fontSize: 20,
              lineHeight: 1,
            }}
          >
            ×
          </button>
        </div>

        <p
          style={{
            margin: 0,
            fontSize: 14,
            color: "var(--text-muted)",
            lineHeight: 1.6,
          }}
        >
          {description}
        </p>

        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <label style={{ fontSize: 13, color: "var(--main-text)" }}>
            Type <strong>{confirmPhrase}</strong> to confirm:
          </label>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={confirmPhrase}
            autoFocus
            style={{
              padding: "0.5rem 0.75rem",
              borderRadius: 8,
              border: `1px solid ${matches ? "#EF4444" : "var(--card-border)"}`,
              background: "var(--main-bg)",
              color: "var(--main-text)",
              fontSize: 13,
              outline: "none",
            }}
          />
        </div>

        <div
          style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}
        >
          <button
            onClick={onClose}
            style={{
              padding: "0.5rem 1rem",
              borderRadius: 8,
              border: "1px solid var(--card-border)",
              background: "var(--main-bg)",
              color: "var(--main-text)",
              fontSize: 13,
              cursor: "pointer",
            }}
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={!matches || isPending}
            style={{
              padding: "0.5rem 1.25rem",
              borderRadius: 8,
              border: "none",
              background: matches && !isPending ? "#EF4444" : "#EF444455",
              color: "#fff",
              fontSize: 13,
              fontWeight: 600,
              cursor: matches && !isPending ? "pointer" : "not-allowed",
            }}
          >
            {isPending ? "Processing…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

function DangerCard({
  title,
  description,
  buttonLabel,
  disabled,
  onClick,
  variant = "default",
}: {
  title: string;
  description: string;
  buttonLabel: string;
  disabled: boolean;
  onClick: () => void;
  variant?: "default" | "critical";
}) {
  const critical = variant === "critical";
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        gap: "1.5rem",
        padding: "1.25rem 1.5rem",
        background: critical ? "#EF444408" : "var(--card-bg)",
        border: `1px solid ${critical ? "#EF444444" : "var(--card-border)"}`,
        borderRadius: 12,
      }}
    >
      <div>
        <div
          style={{
            fontSize: 14,
            fontWeight: 600,
            color: "var(--main-text)",
            marginBottom: 4,
          }}
        >
          {title}
        </div>
        <div
          style={{ fontSize: 13, color: "var(--text-muted)", lineHeight: 1.5 }}
        >
          {description}
        </div>
      </div>
      <button
        onClick={onClick}
        disabled={disabled}
        style={{
          whiteSpace: "nowrap",
          padding: "0.5rem 1.1rem",
          borderRadius: 8,
          border: "none",
          background: disabled
            ? "#EF444433"
            : critical
              ? "#EF4444"
              : "transparent",
          color: disabled ? "var(--text-muted)" : critical ? "#fff" : "#EF4444",
          ...(critical ? {} : { border: "1px solid #EF444466" }),
          fontSize: 13,
          fontWeight: 600,
          cursor: disabled ? "not-allowed" : "pointer",
          opacity: disabled ? 0.5 : 1,
        }}
      >
        {buttonLabel}
      </button>
    </div>
  );
}

export default function DangerZoneActions({ isOwner }: { isOwner: boolean }) {
  const [modal, setModal] = useState<"events" | "account" | null>(null);
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  function confirm() {
    setError(null);
    startTransition(async () => {
      try {
        if (modal === "events") {
          await deleteEvents();
          setModal(null);
        } else if (modal === "account") {
          await deleteAccount();
        }
      } catch (e) {
        if (e instanceof Error && e.message === "NEXT_REDIRECT") return;
        setError(e instanceof Error ? e.message : "Something went wrong.");
      }
    });
  }

  return (
    <>
      <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        <DangerCard
          title="Delete All Events"
          description="Permanently deletes all events, spans, and agent runs for this organization. Agents and their configurations are preserved."
          buttonLabel="Delete Events"
          disabled={!isOwner}
          onClick={() => setModal("events")}
        />
        <DangerCard
          title="Delete Account"
          description="Permanently deletes your organization and everything in it — agents, runs, events, members, and audit logs. This cannot be undone."
          buttonLabel="Delete Account"
          disabled={!isOwner}
          onClick={() => setModal("account")}
          variant="critical"
        />
      </div>

      {error && (
        <p style={{ margin: 0, fontSize: 13, color: "#EF4444" }}>{error}</p>
      )}

      {modal === "events" && (
        <ConfirmModal
          title="Delete All Events"
          description="This will permanently delete all events, spans, and agent runs. Your agents and their configurations will not be affected."
          confirmLabel="Delete Events"
          confirmPhrase="delete events"
          onConfirm={confirm}
          onClose={() => setModal(null)}
          isPending={isPending}
        />
      )}

      {modal === "account" && (
        <ConfirmModal
          title="Delete Account"
          description="This will permanently delete your entire organization including all agents, runs, events, members, and audit logs. There is no going back."
          confirmLabel="Delete Account"
          confirmPhrase="delete my account"
          onConfirm={confirm}
          onClose={() => setModal(null)}
          isPending={isPending}
        />
      )}
    </>
  );
}
