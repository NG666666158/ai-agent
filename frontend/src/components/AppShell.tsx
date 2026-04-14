import type { PropsWithChildren } from "react";

import type { View } from "../routing";

const navItems: Array<{ id: View; label: string; kicker: string }> = [
  { id: "console", label: "控制台", kicker: "发起任务" },
  { id: "tasks", label: "任务", kicker: "查看结果" },
  { id: "memories", label: "记忆", kicker: "向量检索" },
  { id: "settings", label: "设置", kicker: "运行状态" },
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
        <h1>Orion Agent 中文控制台</h1>
        <p className="sub">
          这里用于发起任务、观察执行进度、查看最终结果、检索长期记忆，并检查系统当前的运行状态。
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
