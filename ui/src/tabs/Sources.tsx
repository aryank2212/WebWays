import { useCallback, useEffect, useState } from "react";
import { api, Source } from "../api";

export default function SourcesTab() {
  const [sources, setSources] = useState<Source[]>([]);
  const [url, setUrl] = useState("");
  const [msg, setMsg] = useState("");
  const refresh = useCallback(() => api.sources().then(setSources).catch((e) => setMsg(String(e))), []);
  useEffect(() => { refresh(); }, [refresh]);

  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    try { const s = await api.addSource(url); setUrl(""); setMsg(`Added ${s.name}.`); refresh(); } catch (err) { setMsg(String(err)); }
  };

  return (
    <section>
      <div className="card">
        <h2>Index sources</h2>
        <p className="small">
          An index source is a server run by someone else that lists torrents. Swarm has none built in and
          verifies every listing’s signature itself, but each operator decides what they carry — you decide which
          operators you trust. Adding a source here is your choice.
        </p>
        <form onSubmit={add} className="row">
          <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://index.example.org" />
          <button className="primary" disabled={!url}>Add</button>
        </form>
        {msg && <p className="notice">{msg}</p>}
      </div>
      {sources.map((s) => (
        <article key={s.url} className="card">
          <div className="row between">
            <strong>{s.name}</strong>
            <label className="row small">
              <input type="checkbox" checked={s.enabled} onChange={(e) => api.toggleSource(s.url, e.target.checked).then(refresh)} />
              enabled
            </label>
          </div>
          <p className="small muted">{s.url}{s.takedown_contact && ` · takedown contact: ${s.takedown_contact}`}</p>
          <button onClick={() => confirm(`Remove ${s.name}?`) && api.removeSource(s.url).then(refresh)}>Remove</button>
        </article>
      ))}
    </section>
  );
}
