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
        <h2>Runtime config</h2>
        <pre>{runtime ? JSON.stringify(runtime, null, 2) : "Loading..."}</pre>
      </section>
      <section className="panel">
        <h2>Health status</h2>
        <pre>{health ? JSON.stringify(health, null, 2) : "Loading..."}</pre>
      </section>
    </section>
  );
}
