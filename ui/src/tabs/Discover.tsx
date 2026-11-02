import { useEffect, useState } from "react";
import { api, SearchItem, Source } from "../api";
import type { PlayerTarget } from "../Player";
import { isMedia } from "../api";

export default function Discover({ onPlay, goto }: { onPlay: (t: PlayerTarget) => void; goto: (t: string) => void }) {
  const [sources, setSources] = useState<Source[] | null>(null);
  const [q, setQ] = useState("");
  const [items, setItems] = useState<SearchItem[] | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState("");

  useEffect(() => { api.sources().then(setSources).catch((e) => setMsg(String(e))); }, []);

  const search = async (e: React.FormEvent) => {
    e.preventDefault();
    setMsg("");
    try {
      const r = await api.search(q);
      setItems(r.items);
      setErrors(r.errors);
    } catch (err) { setMsg(String(err)); }
  };

  const add = async (it: SearchItem, stream: boolean) => {
    try {
      const t = await api.addInfohash(it.listing.infohash, it.listing.title);
      if (!stream) { setMsg(`Added “${it.listing.title}” to Downloads.`); return; }
      const files = (await api.torrent(t.infohash)).files.filter((f) => isMedia(f.path));
      if (!files.length) { setMsg("Added, but no playable media file was found in it."); return; }
      const biggest = files.reduce((a, b) => (b.size > a.size ? b : a));
      onPlay({ title: it.listing.title, url: biggest.stream_url, path: biggest.path });
    } catch (err) { setMsg(String(err)); }
  };

  const report = async (it: SearchItem) => {
    const category = prompt("Report as: copyright, illegal, malware, spam or other?", "copyright");
    if (!category) return;
    try {
      await api.report(it.sources[0].url, it.id, category.trim(), prompt("Details (optional)") ?? "");
      setMsg(`Reported to ${it.sources[0].name}'s operator.`);
    } catch (err) { setMsg(String(err)); }
  };

  const rate = async (it: SearchItem) => {
    const s = Number(prompt("Rate 1–5", "5"));
    if (!(s >= 1 && s <= 5)) return;
    try { await api.rate(it.sources[0].url, it.id, s); setMsg("Rating sent."); } catch (err) { setMsg(String(err)); }
  };

  if (sources && sources.length === 0) {
    return (
      <section className="card narrow">
        <h2>No index sources yet</h2>
        <p>
          WebWays doesn’t ship with a catalogue. Discovery works through index nodes that you choose to add —
          each one is run by someone else under their own rules. Add one to start searching.
        </p>
        <button className="primary" onClick={() => goto("Sources")}>Add an index source</button>
        <p className="muted small">You can still paste a magnet link on the Downloads tab without any source.</p>
      </section>
    );
  }

  return (
    <section>
      <form onSubmit={search} className="row">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search listings…" autoFocus />
        <button className="primary">Search</button>
      </form>
      {msg && <p className="notice">{msg}</p>}
      {Object.entries(errors).map(([u, e]) => <p key={u} className="warn small">{u}: {e}</p>)}
      {items?.length === 0 && <p className="muted">Nothing found.</p>}
      {items?.map((it) => (
        <article key={it.id} className="card">
          <div className="row between">
            <h3>{it.listing.title}</h3>
            {it.listing.price && <span className="badge">{(it.listing.price.amount / 100).toFixed(2)} {it.listing.price.currency}</span>}
          </div>
          <p>{it.listing.description}</p>
          <p className="small muted">
            {it.listing.license} · publisher <code title={it.listing.publisher}>{it.listing.publisher.slice(0, 10)}…</code>
            {it.verified_by.map((v) => (
              <span key={v.node} className="badge ok" title="A claim made by that index node, not proof">
                {" "}✓ {v.name} (per {v.node})
              </span>
            ))}
            {it.rating && ` · ★ ${it.rating.average} (${it.rating.count}, per ${it.rating.node})`}
          </p>
          <p className="small">{it.listing.tags.map((t) => <span key={t} className="tag">{t}</span>)}</p>
          <p className="small muted">Listed on {it.sources.map((s) => s.name).join(", ")}</p>
          <div className="row">
            <button className="primary" onClick={() => add(it, false)}>Download</button>
            <button onClick={() => add(it, true)}>Stream</button>
            <button onClick={() => rate(it)}>Rate</button>
            <button onClick={() => report(it)}>Report</button>
          </div>
        </article>
      ))}
    </section>
  );
}
