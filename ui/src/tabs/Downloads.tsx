import { useCallback, useEffect, useState } from "react";
import { api, fmtBytes, isMedia, Settings, TFile, Torrent } from "../api";
import type { PlayerTarget } from "../Player";

export default function Downloads({ onPlay }: { onPlay: (t: PlayerTarget) => void }) {
  const [list, setList] = useState<Torrent[]>([]);
  const [open, setOpen] = useState<string | null>(null);
  const [files, setFiles] = useState<TFile[]>([]);
  const [magnet, setMagnet] = useState("");
  const [msg, setMsg] = useState("");
  const [settings, setSettings] = useState<Settings | null>(null);

  const [filesFor, setFilesFor] = useState<string | null>(null);
  const refresh = useCallback(() => {
    api.torrents().then(setList).catch((e) => setMsg(String(e)));
    if (open) api.torrent(open).then((t) => { setFiles(t.files); setFilesFor(open); }).catch(() => setFiles([]));
  }, [open]);
  useEffect(() => { refresh(); const id = setInterval(refresh, 2000); return () => clearInterval(id); }, [refresh]);
  useEffect(() => { api.settings().then(setSettings).catch(() => undefined); }, []);

  const addMagnet = async (e: React.FormEvent) => {
    e.preventDefault();
    try { await api.addMagnet(magnet.trim()); setMagnet(""); setMsg(""); refresh(); } catch (err) { setMsg(String(err)); }
  };
  const run = (p: Promise<unknown>) => p.then(refresh).catch((e) => setMsg(String(e)));
  const save = (patch: Partial<Settings>) => api.saveSettings(patch).then(setSettings).catch((e) => setMsg(String(e)));

  return (
    <section>
      <form onSubmit={addMagnet} className="row">
        <input value={magnet} onChange={(e) => setMagnet(e.target.value)} placeholder="Paste a magnet link…" />
        <button className="primary" disabled={!magnet}>Add</button>
      </form>
      {msg && <p className="warn">{msg}</p>}
      {list.length === 0 && <p className="muted">Nothing here yet.</p>}
      {list.map((t) => (
        <article key={t.infohash} className="card">
          <div className="row between">
            <strong className="grow" onClick={() => setOpen(open === t.infohash ? null : t.infohash)} style={{ cursor: "pointer" }}>
              {t.name}
            </strong>
            <span className="badge">{t.state}</span>
          </div>
          <progress value={t.progress} max={1} />
          <p className="small muted">
            {(t.progress * 100).toFixed(1)}% of {fmtBytes(t.size)} · ↓ {fmtBytes(t.download_rate)}/s · ↑ {fmtBytes(t.upload_rate)}/s ·
            {" "}{t.peers} peers{t.eta ? ` · ${Math.ceil(t.eta / 60)} min left` : ""}
          </p>
          {t.error && <p className="warn small">{t.error}</p>}
          <div className="row">
            {t.state === "paused"
              ? <button onClick={() => run(api.action(t.infohash, "resume"))}>Resume</button>
              : <button onClick={() => run(api.action(t.infohash, "pause"))}>Pause</button>}
            <button onClick={() => confirm(`Remove “${t.name}”? Downloaded files are kept.`) && run(api.remove(t.infohash, false))}>Remove</button>
            <button onClick={() => confirm(`Remove “${t.name}” AND delete its files?`) && run(api.remove(t.infohash, true))}>Delete files</button>
          </div>
          {open === t.infohash && (
            <ul className="files">
              {(filesFor !== t.infohash || files.length === 0) && <li className="muted small">Loading files…</li>}
              {filesFor === t.infohash && files.map((f) => (
                <li key={f.index} className="row between small">
                  <span className="grow">{f.path} <span className="muted">({fmtBytes(f.size)}, {(f.progress * 100).toFixed(0)}%)</span></span>
                  {isMedia(f.path)
                    ? <button onClick={() => onPlay({ title: f.path, url: f.stream_url, path: f.path })}>Play</button>
                    : <a href={f.stream_url} download>Save</a>}
                </li>
              ))}
            </ul>
          )}
        </article>
      ))}
      {settings && (
        <details className="card">
          <summary>Settings</summary>
          <label>Encryption
            <select value={settings.encryption} onChange={(e) => save({ encryption: e.target.value })}>
              <option value="enabled">Prefer encrypted, allow plain</option>
              <option value="forced">Require encrypted peers</option>
            </select>
          </label>
          <label>Download limit (KB/s, 0 = none)
            <input type="number" min={0} defaultValue={settings.download_limit / 1024}
                   onBlur={(e) => save({ download_limit: Math.round(Number(e.target.value) * 1024) })} />
          </label>
          <label>Upload limit (KB/s, 0 = none)
            <input type="number" min={0} defaultValue={settings.upload_limit / 1024}
                   onBlur={(e) => save({ upload_limit: Math.round(Number(e.target.value) * 1024) })} />
          </label>
          <p className="small muted">Saving to {settings.download_dir}</p>
        </details>
      )}
    </section>
  );
}
