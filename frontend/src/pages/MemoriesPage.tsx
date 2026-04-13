import { useEffect, useState } from "react";

import { searchMemories, type MemoryRecord } from "../api";

export function MemoriesPage() {
  const [query, setQuery] = useState("agent roadmap");
  const [scope, setScope] = useState("default");
  const [memories, setMemories] = useState<MemoryRecord[]>([]);

  const loadMemories = async () => {
    setMemories(await searchMemories(query, scope));
  };

  useEffect(() => {
    void loadMemories();
  }, []);

  return (
    <section className="panel">
      <h2>Vector memory search</h2>
      <div className="actions">
        <input value={query} onChange={(event) => setQuery(event.target.value)} />
        <input value={scope} onChange={(event) => setScope(event.target.value)} />
        <button onClick={() => void loadMemories()}>Search</button>
      </div>
      <div className="list" style={{ marginTop: 16 }}>
        {memories.map((memory) => (
          <article className="card" key={memory.id}>
            <h3>{memory.topic}</h3>
            <div className="meta">
              {memory.scope} · {new Date(memory.created_at).toLocaleString()}
            </div>
            <pre>{memory.summary}</pre>
            <pre>{memory.details}</pre>
          </article>
        ))}
      </div>
    </section>
  );
}
