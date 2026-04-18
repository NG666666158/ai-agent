import { useEffect, useState } from "react";

import { getHealthInfo, getRuntimeInfo, type HealthInfo, type RuntimeInfo } from "../api";

function formatJson(value: unknown) {
  return JSON.stringify(value, null, 2);
}

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
        <div className="panel-head">
          <div>
            <h2>运行配置</h2>
            <div className="meta">展示后端当前暴露的运行参数、模型配置和环境信息。</div>
          </div>
        </div>
        <pre>{runtime ? formatJson(runtime) : "正在加载运行配置..."}</pre>
      </section>
      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>健康状态</h2>
            <div className="meta">用于快速确认服务、依赖组件和接口健康情况。</div>
          </div>
        </div>
        <pre>{health ? formatJson(health) : "正在加载健康状态..."}</pre>
      </section>
    </section>
  );
}
