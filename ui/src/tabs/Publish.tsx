import { useEffect, useState } from "react";
import { api, Source, Torrent } from "../api";

const LICENSES = ["CC0-1.0", "CC-BY-4.0", "CC-BY-SA-4.0", "CC-BY-NC-4.0", "MIT", "Apache-2.0", "GPL-3.0-or-later", "LicenseRef-Proprietary"];

export default function Publish({ prefill }: { prefill?: { infohash: string; title: string } | null }) {
  const [pub, setPub] = useState<string | null | undefined>(undefined);
  const [torrents, setTorrents] = useState<Torrent[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [msg, setMsg] = useState("");
  const [path, setPath] = useState("");
  const [f, setF] = useState({ infohash: prefill?.infohash ?? "", title: prefill?.title ?? "", description: "", tags: "", license: "", price: "", source: "" });
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setF((p) => ({ ...p, [k]: e.target.value }));

  useEffect(() => {
    api.identity().then((i) => setPub(i.public_key)).catch((e) => setMsg(String(e)));
    api.torrents().then(setTorrents).catch(() => undefined);
    api.sources().then(setSources).catch(() => undefined);
  }, []);

  const createId = () => api.createIdentity().then((i) => setPub(i.public_key)).catch((e) => setMsg(String(e)));
  const seed = async () => {
    try { const t = await api.create(path, ""); setTorrents([t, ...torrents]); setF({ ...f, infohash: t.infohash, title: f.title || t.name }); setMsg(`Seeding ${t.name}.`); }
    catch (err) { setMsg(String(err)); }
  };
  const publish = async (e: React.FormEvent) => {
    e.preventDefault();
    const tags = f.tags.split(",").map((t) => t.trim().toLowerCase()).filter(Boolean);
    const price = f.price ? { amount: Math.round(Number(f.price) * 100), currency: "USD" } : undefined;
    try {
      const r = await api.publish({ infohash: f.infohash, title: f.title, description: f.description, tags, license: f.license, price, source: f.source || undefined });
      setMsg(`Signed and ${f.source ? "published" : "created"} listing ${r.id.slice(0, 12)}…`);
    } catch (err) { setMsg(String(err)); }
  };

  if (pub === undefined) return <p className="muted">Loading…</p>;
  if (pub === null) {
    return (
      <section className="card narrow">
        <h2>Publisher identity</h2>
        <p>Listings are signed with a key that stays on this machine. Your public key <em>is</em> your publisher identity; there are no accounts.</p>
        <button className="primary" onClick={createId}>Create identity</button>
        {msg && <p className="warn">{msg}</p>}
      </section>
    );
  }
  return (
    <section>
      <div className="card">
        <p className="small">Your publisher key: <code>{pub}</code></p>
        <h3>1 · Pick what to share</h3>
        <div className="row">
          <input value={path} onChange={(e) => setPath(e.target.value)} placeholder="Path of a file or folder to seed, e.g. /home/me/film.mp4" />
          <button onClick={seed} disabled={!path}>Create &amp; seed</button>
        </div>
        <label>…or choose an existing torrent
          <select value={f.infohash} onChange={set("infohash")}>
            <option value="">—</option>
            {f.infohash && !torrents.some((t) => t.infohash === f.infohash) && <option value={f.infohash}>{f.infohash.slice(0, 12)}… (from Create)</option>}
            {torrents.map((t) => <option key={t.infohash} value={t.infohash}>{t.name}</option>)}
          </select>
        </label>
      </div>
      <form className="card" onSubmit={publish}>
        <h3>2 · Describe and sign</h3>
        <p className="small muted">Only list content you have the right to distribute, and choose the license that matches.</p>
        <label>Title<input value={f.title} onChange={set("title")} required maxLength={200} /></label>
        <label>Description<textarea value={f.description} onChange={set("description")} rows={3} maxLength={4000} /></label>
        <label>Tags (comma separated)<input value={f.tags} onChange={set("tags")} /></label>
        <label>License<input list="licenses" value={f.license} onChange={set("license")} required />
          <datalist id="licenses">{LICENSES.map((l) => <option key={l} value={l} />)}</datalist></label>
        <label>Price in USD (optional)<input type="number" min={0} step="0.01" value={f.price} onChange={set("price")} /></label>
        <label>Publish to
          <select value={f.source} onChange={set("source")}>
            <option value="">(just sign it, don't send)</option>
            {sources.map((s) => <option key={s.url} value={s.url}>{s.name}</option>)}
          </select>
        </label>
        <button className="primary" disabled={!f.infohash}>Sign &amp; publish</button>
      </form>
      {msg && <p className="notice">{msg}</p>}
    </section>
  );
}
