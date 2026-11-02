import { useCallback, useEffect, useState } from "react";
import { api, hasToken } from "./api";
import Discover from "./tabs/Discover";
import Downloads from "./tabs/Downloads";
import Create from "./tabs/Create";
import Publish from "./tabs/Publish";
import SourcesTab from "./tabs/Sources";
import Player, { PlayerTarget } from "./Player";

const TABS = ["Discover", "Downloads", "Create", "Publish", "Sources"] as const;
type Tab = (typeof TABS)[number];

export default function App() {
  const [tab, setTab] = useState<Tab>("Discover");
  const [prefill, setPrefill] = useState<{ infohash: string; title: string } | null>(null);
  const [player, setPlayer] = useState<PlayerTarget | null>(null);
  const [status, setStatus] = useState<Awaited<ReturnType<typeof api.status>> | null>(null);

  useEffect(() => {
    if (!hasToken) return;
    const tick = () => api.status().then(setStatus).catch(() => setStatus(null));
    tick();
    const id = setInterval(tick, 3000);
    return () => clearInterval(id);
  }, []);

  const play = useCallback((t: PlayerTarget) => setPlayer(t), []);

  if (!hasToken) {
    return (
      <main className="narrow">
        <h1>Swarm</h1>
        <p>
          This page needs the local API token. Start the daemon with <code>swarm-core serve</code> and open the
          address it prints (it ends in <code>#token=…</code>).
        </p>
      </main>
    );
  }

  return (
    <>
      <header>
        <strong className="brand">Swarm</strong>
        <nav>
          {TABS.map((t) => (
            <button key={t} className={t === tab ? "active" : ""} onClick={() => setTab(t)}>{t}</button>
          ))}
        </nav>
        <span className="muted small">
          {status ? `↓ ${(status.download_rate / 1024).toFixed(0)} KB/s · ↑ ${(status.upload_rate / 1024).toFixed(0)} KB/s` : "daemon offline"}
        </span>
      </header>
      <main>
        {tab === "Discover" && <Discover onPlay={play} goto={(t) => setTab(t as Tab)} />}
        {tab === "Downloads" && <Downloads onPlay={play} />}
        {tab === "Create" && <Create onPublish={(infohash, title) => { setPrefill({ infohash, title }); setTab("Publish"); }} />}
        {tab === "Publish" && <Publish prefill={prefill} />}
        {tab === "Sources" && <SourcesTab />}
      </main>
      {player && <Player target={player} onClose={() => setPlayer(null)} />}
    </>
  );
}
