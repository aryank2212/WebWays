import { useRef, useState } from "react";
import { api, fmtBytes } from "../api";
import { downloadBlob, fromDrop, fromInput, inspect, isJunk, make, Made, parseList, Picked, suggestName, toBase64, validateUrls } from "../lib/maker";

const PIECES: [string, number][] = [["Automatic", 0], ["256 KiB", 1 << 18], ["1 MiB", 1 << 20], ["4 MiB", 1 << 22], ["16 MiB", 1 << 24]];

export default function Create({ onPublish }: { onPublish: (infohash: string, title: string) => void }) {
  const [files, setFiles] = useState<Picked[]>([]);
  const [over, setOver] = useState(false);
  const [name, setName] = useState("");
  const [comment, setComment] = useState("");
  const [priv, setPriv] = useState(false);
  const [piece, setPiece] = useState(0);
  const [trackers, setTrackers] = useState("");
  const [webSeeds, setWebSeeds] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [made, setMade] = useState<Made | null>(null);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const dirInput = useRef<HTMLInputElement>(null);

  const [skipped, setSkipped] = useState(0);
  const add = (picked: Picked[]) => {
    setErr(""); setMsg("");
    const more = picked.filter((f) => !isJunk(f));          // same rule the torrent builder applies
    setSkipped((n) => n + picked.length - more.length);
    const all = [...files, ...more];
    setFiles(all);
    setMade(null);
    if (!name) setName(suggestName(all));
  };
  const onDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setOver(false);
    try { add(await fromDrop(e.dataTransfer)); } catch (x) { setErr(String(x)); }
  };
  const total = files.reduce((n, f) => n + f.size, 0);

  const create = async () => {
    setErr(""); setMsg("");
    const t = trackers ? parseList(trackers) : [];
    const w = webSeeds ? parseList(webSeeds) : [];
    const bad = validateUrls(t, /^(udp|https?|wss?):\/\/\S+$/) ?? validateUrls(w, /^https?:\/\/\S+$/);
    if (bad) { setErr(bad); return; }
    try {
      setBusy("Hashing files…"); setProgress(0);
      const r = await make(files, { name: name.trim(), comment, private: priv, pieceLength: piece, trackers: t, webSeeds: w },
        (done, tot) => setProgress(tot ? done / tot : 0));
      setMade(r);
    } catch (x) { setErr(String(x instanceof Error ? x.message : x)); } finally { setBusy(null); }
  };

  const seed = async () => {
    if (!made) return;
    setErr(""); setMsg("");
    let key = "";
    try {
      const prep = await api.seedPrepare(toBase64(made.torrent));
      key = prep.infohash;
      if (prep.files.length !== made.kept.length) throw new Error("file list mismatch; please recreate the torrent");
      let sent = 0; setProgress(0);
      for (const f of prep.files) {
        const src = made.kept[f.index];
        if (!src || src.size !== f.size) throw new Error(`file ${f.path} changed size; please recreate the torrent`);
        setBusy(`Copying ${f.path}…`);
        await api.seedPut(key, f.index, src);
        sent += f.size; setProgress(total ? sent / total : 1);
      }
      setBusy("Verifying…");
      await api.seedFinish(key);
      setMsg("Seeding. Your client verified every piece against the torrent. Keep it running so others can download.");
    } catch (x) {
      if (key) api.seedCancel(key).catch(() => undefined);
      setErr(String(x instanceof Error ? x.message : x));
    } finally { setBusy(null); }
  };

  const copy = (text: string) => navigator.clipboard.writeText(text).then(() => setMsg("Copied."), () => setMsg("Copy failed; select the text instead."));

  return (
    <section>
      <div className="card">
        <h2>Create a torrent</h2>
        <p className="small muted">
          Free, no account. Files are hashed in this browser tab; nothing is uploaded unless you press “Seed from this device”.
          No trackers are added unless you list them, so peers are found through DHT.
        </p>
        <div
          className={`drop ${over ? "over" : ""}`}
          data-testid="dropzone"
          onDragOver={(e) => { e.preventDefault(); setOver(true); }}
          onDragLeave={() => setOver(false)}
          onDrop={onDrop}
        >
          <strong>Drop files or a folder here</strong>
          <div className="row" style={{ justifyContent: "center" }}>
            <button type="button" onClick={() => fileInput.current?.click()}>Choose files</button>
            <button type="button" onClick={() => dirInput.current?.click()}>Choose folder</button>
          </div>
          <input ref={fileInput} type="file" multiple hidden data-testid="file-input"
                 onChange={(e) => { if (e.target.files) add(fromInput(e.target.files)); e.target.value = ""; }} />
          <input ref={dirInput} type="file" hidden data-testid="dir-input"
                 {...({ webkitdirectory: "", directory: "" } as Record<string, string>)}
                 onChange={(e) => { if (e.target.files) add(fromInput(e.target.files)); e.target.value = ""; }} />
        </div>
        {files.length > 0 && (
          <>
            <p className="small">{files.length} file{files.length > 1 ? "s" : ""}, {fmtBytes(total)}{skipped > 0 && <span className="muted"> ({skipped} hidden system file{skipped > 1 ? "s" : ""} skipped)</span>} <button className="link" onClick={() => { setFiles([]); setMade(null); setName(""); setSkipped(0); setErr(""); setMsg(""); }}>clear</button></p>
            <ul className="files small">
              {files.slice(0, 8).map((f, i) => <li key={i}>{(f.fullPath ?? f.name).replace(/^\//, "")} <span className="muted">({fmtBytes(f.size)})</span></li>)}
              {files.length > 8 && <li className="muted">…and {files.length - 8} more</li>}
            </ul>
          </>
        )}
      </div>

      {files.length > 0 && (
        <div className="card">
          <label>Name<input value={name} onChange={(e) => setName(e.target.value)} placeholder="shown to downloaders" /></label>
          <label>Comment (optional)<input value={comment} onChange={(e) => setComment(e.target.value)} maxLength={500} /></label>
          <label>Piece size
            <select value={piece} onChange={(e) => setPiece(Number(e.target.value))}>
              {PIECES.map(([l, v]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <details>
            <summary className="small">Advanced: trackers, web seeds, private</summary>
            <label>Trackers (one per line, optional)
              <textarea rows={2} value={trackers} onChange={(e) => setTrackers(e.target.value)} placeholder="udp://tracker.example.org:6969/announce" />
            </label>
            <p className="small muted">A tracker learns the address of everyone using this torrent. Leave empty to rely on DHT only.</p>
            <label>Web seeds (one per line, optional)
              <textarea rows={2} value={webSeeds} onChange={(e) => setWebSeeds(e.target.value)} placeholder="https://cdn.example.org/files/" />
            </label>
            <label className="row"><input type="checkbox" checked={priv} onChange={(e) => setPriv(e.target.checked)} /> Private torrent (disables DHT/PEX; requires a tracker)</label>
          </details>
          <button className="primary" onClick={create} disabled={!!busy || !name.trim()}>Create torrent</button>
        </div>
      )}

      {busy && <div className="card"><p>{busy}</p><progress value={progress} max={1} /></div>}
      {err && <p className="warn" role="alert">{err}</p>}
      {msg && <p className="notice">{msg}</p>}

      {made && (
        <div className="card" data-testid="result">
          <h3>{made.parsed.name}</h3>
          <p className="small">Info hash <code data-testid="infohash">{made.parsed.infoHash}</code></p>
          <label>Magnet link<textarea readOnly rows={3} value={made.magnet} data-testid="magnet" onFocus={(e) => e.target.select()} /></label>
          <div className="row">
            <button onClick={() => copy(made.magnet)}>Copy magnet</button>
            <button onClick={() => downloadBlob(made.torrent, `${made.parsed.name ?? made.parsed.infoHash}.torrent`)}>Download .torrent</button>
            <button className="primary" onClick={seed} disabled={!!busy}>Seed from this device</button>
            <button onClick={() => onPublish(made.parsed.infoHash, made.parsed.name ?? "")}>List it on an index…</button>
          </div>
          <p className="small muted">
            A magnet or .torrent only describes the files. Someone has to be seeding before anyone can download:
            “Seed from this device” copies them into your client’s download folder and starts sharing.
            Only share files you have the right to distribute.
          </p>
        </div>
      )}

      <Inspector />
    </section>
  );
}

function Inspector() {
  const [text, setText] = useState("");
  const [out, setOut] = useState<Awaited<ReturnType<typeof inspect>> | null>(null);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");

  const run = async (input: string | Uint8Array) => {
    setErr(""); setMsg("");
    try { setOut(await inspect(input)); } catch (x) { setOut(null); setErr("That doesn’t look like a magnet link, info hash or .torrent file."); void x; }
  };
  const onDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    const f = e.dataTransfer.files[0];
    if (f) run(new Uint8Array(await f.arrayBuffer()));
  };
  return (
    <div className="card" onDragOver={(e) => e.preventDefault()} onDrop={onDrop} data-testid="inspector">
      <h3>Convert or inspect</h3>
      <p className="small muted">Drop a .torrent file here, or paste a magnet link or info hash, to get the other form and see what’s inside.</p>
      <div className="row">
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="magnet:?xt=urn:btih:…" data-testid="inspect-input" />
        <button onClick={() => run(text.trim())} disabled={!text.trim()}>Inspect</button>
      </div>
      {err && <p className="warn small">{err}</p>}
      {out && (
        <div data-testid="inspect-result">
          <p><strong>{out.parsed.name ?? "(no name in link)"}</strong> <span className="small muted">{out.parsed.length ? fmtBytes(out.parsed.length) : ""}</span></p>
          <p className="small">Info hash <code>{out.parsed.infoHash}</code></p>
          <p className="small muted">{out.parsed.announce?.length ? `Trackers: ${out.parsed.announce.join(", ")}` : "No trackers: peers are found through DHT."}</p>
          {out.parsed.files && <p className="small muted">{out.parsed.files.length} file(s)</p>}
          <textarea readOnly rows={2} value={out.magnet} />
          <div className="row">
            <button onClick={() => navigator.clipboard.writeText(out.magnet).then(() => setMsg("Copied."))}>Copy magnet</button>
            {out.torrent && <button onClick={() => downloadBlob(out.torrent!, `${out.parsed.infoHash}.torrent`)}>Save .torrent</button>}
            <button className="primary" onClick={() => api.addMagnet(out.magnet).then(() => setMsg("Added to Downloads.")).catch((x) => setErr(String(x)))}>Add to my client</button>
          </div>
          {msg && <p className="notice small">{msg}</p>}
        </div>
      )}
    </div>
  );
}
