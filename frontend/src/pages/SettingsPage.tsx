import { useEffect, useState } from "react";

import { getHealthInfo, getRuntimeInfo, type HealthInfo, type RuntimeInfo } from "../api";

export function SettingsPage() {
  const [runtime, setRuntime] = useState<RuntimeInfo | null>(null);
  const [health, setHealth] = useState<HealthInfo | null>(null);

  useEffect(() => {
    void (async () => {
      setRuntime(await getRuntimeInfo());
      setHealth(await getHealthInfo());
    })();
  }, []);

  return (
    <section className="grid">
      <section className="panel">
        <h2>运行配置</h2>
        <pre>{runtime ? JSON.stringify(runtime, null, 2) : "加载中..."}</pre>
      </section>
      <section className="panel">
        <h2>健康状态</h2>
        <pre>{health ? JSON.stringify(health, null, 2) : "加载中..."}</pre>
      </section>
    </section>
  );
}
