import type { PropsWithChildren } from "react";

import type { View } from "../routing";

const navItems: Array<{ id: View; label: string; kicker: string }> = [
  { id: "console", label: "Console", kicker: "Run tasks" },
  { id: "tasks", label: "Tasks", kicker: "Inspect output" },
  { id: "memories", label: "Memories", kicker: "Vector recall" },
  { id: "settings", label: "Settings", kicker: "Runtime status" },
];

type AppShellProps = PropsWithChildren<{
  currentView: View;
  onNavigate: (view: View) => void;
}>;

export function AppShell({ currentView, onNavigate, children }: AppShellProps) {
  return (
    <div className="shell">
      <section className="hero">
        <div className="eyebrow">Orion Agent</div>
        <h1>Production-ready frontend workspace</h1>
        <p className="sub">
          A formal React + Vite control surface for task execution, memory retrieval, and runtime
          diagnostics.
        </p>
        <nav className="nav">
          {navItems.map((item) => (
            <button
              key={item.id}
              className={item.id === currentView ? "nav-button active" : "nav-button"}
              onClick={() => onNavigate(item.id)}
            >
              <strong>{item.label}</strong>
              <span>{item.kicker}</span>
            </button>
          ))}
        </nav>
      </section>
      {children}
    </div>
  );
}
