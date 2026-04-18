import type { PropsWithChildren } from "react";

import type { View } from "../routing";

const navItems: Array<{ id: View; label: string; kicker: string }> = [
  { id: "console", label: "对话控制台", kicker: "发起任务并查看回答" },
  { id: "tasks", label: "任务中心", kicker: "查看执行详情" },
  { id: "sessions", label: "会话历史", kicker: "追溯上下文与分支" },
  { id: "memories", label: "记忆管理", kicker: "浏览、编辑与维护记忆" },
  { id: "profile", label: "用户画像", kicker: "查看跨会话偏好与画像" },
  { id: "settings", label: "系统设置", kicker: "查看运行状态与配置" },
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
          这里可以发起任务、管理聊天会话、追溯历史上下文、维护长期记忆，并查看系统当前的运行状态。
        </p>
        <nav className="nav">
          {navItems.map((item) => (
            <button
              className={item.id === currentView ? "nav-button active" : "nav-button"}
              key={item.id}
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
