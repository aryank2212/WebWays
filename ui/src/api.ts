// The UI's only contact with the outside world: the local daemon's REST API.
export interface Torrent {
  infohash: string; name: string; state: string; progress: number; size: number; downloaded: number;
  download_rate: number; upload_rate: number; peers: number; seeds: number; has_metadata: boolean;
  eta: number | null; error: string | null; magnet: string | null;
}
export interface TFile { index: number; path: string; size: number; priority: number; progress: number; stream_url: string }
export interface Listing {
  v: 1; infohash: string; title: string; description: string; tags: string[]; license: string;
  publisher: string; created: number; seq: number; price?: { amount: number; currency: string };
}
export interface SearchItem {
  id: string; listing: Listing; sources: { name: string; url: string }[];
  verified_by: { node: string; name: string }[]; rating: { average: number; count: number; node: string } | null;
}
export interface Source { url: string; name: string; enabled: boolean; takedown_contact: string }
export interface Settings { download_dir: string; listen_port: number; encryption: string; download_limit: number; upload_limit: number }

// The token arrives in the URL fragment (never sent to any server) and lives only for this tab.
function loadToken(): string {
  const m = /token=([\w-]+)/.exec(location.hash);
  if (m) {
    sessionStorage.setItem("webways-token", m[1]);
    history.replaceState(null, "", location.pathname);
  }
  return sessionStorage.getItem("webways-token") ?? "";
}
const token = loadToken();
export const hasToken = token !== "";

export class ApiError extends Error {}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: { Authorization: `Bearer ${token}`, ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(data?.error?.message ?? `HTTP ${res.status}`);
  return data as T;
}

export const api = {
  torrents: () => call<{ torrents: Torrent[] }>("GET", "/api/torrents").then((r) => r.torrents),
  torrent: (k: string) => call<Torrent & { files: TFile[] }>("GET", `/api/torrents/${k}`),
  addInfohash: (infohash: string, name: string) => call<Torrent>("POST", "/api/torrents", { infohash, name }),
  addMagnet: (magnet: string) => call<Torrent>("POST", "/api/torrents", { magnet }),
  action: (k: string, a: "pause" | "resume") => call<Torrent>("POST", `/api/torrents/${k}/${a}`),
  remove: (k: string, files: boolean) => call<unknown>("DELETE", `/api/torrents/${k}?delete_files=${files ? 1 : 0}`),
  create: (path: string, comment: string) => call<Torrent>("POST", "/api/create", { path, comment }),
  sources: () => call<{ sources: Source[] }>("GET", "/api/sources").then((r) => r.sources),
  addSource: (url: string) => call<Source>("POST", "/api/sources", { url }),
  toggleSource: (url: string, enabled: boolean) => call<unknown>("PUT", "/api/sources", { url, enabled }),
  removeSource: (url: string) => call<unknown>("DELETE", `/api/sources?url=${encodeURIComponent(url)}`),
  search: (q: string) =>
    call<{ items: SearchItem[]; errors: Record<string, string> }>("GET", `/api/search?q=${encodeURIComponent(q)}`),
  report: (source: string, listing: string, category: string, detail: string) =>
    call<unknown>("POST", "/api/report", { source, listing, category, detail }),
  rate: (source: string, listing: string, score: number) => call<unknown>("POST", "/api/rate", { source, listing, score }),
  identity: () => call<{ public_key: string | null }>("GET", "/api/identity"),
  createIdentity: () => call<{ public_key: string }>("POST", "/api/identity"),
  publish: (b: Record<string, unknown>) => call<{ id: string }>("POST", "/api/publish", b),
  seedPrepare: (torrent_b64: string) =>
    call<{ infohash: string; name: string; files: { index: number; path: string; size: number }[] }>("POST", "/api/seed/prepare", { torrent_b64 }),
  seedPut: async (key: string, index: number, file: Blob) => {
    const res = await fetch(`/api/seed/${key}/files/${index}`, { method: "PUT", headers: { Authorization: `Bearer ${token}` }, body: file });
    if (!res.ok) throw new ApiError(((await res.json().catch(() => ({}))) as { error?: { message?: string } }).error?.message ?? `HTTP ${res.status}`);
  },
  seedFinish: (key: string) => call<Torrent>("POST", `/api/seed/${key}/finish`),
  seedCancel: (key: string) => call<unknown>("DELETE", `/api/seed/${key}`),
  settings: () => call<Settings>("GET", "/api/settings"),
  saveSettings: (s: Partial<Settings>) => call<Settings>("PUT", "/api/settings", s),
  status: () => call<{ version: string; download_rate: number; upload_rate: number; dht_nodes: number }>("GET", "/api/status"),
};

export const fmtBytes = (n: number) => {
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(n >= 100 || i === 0 ? 0 : 1)} ${u[i]}`;
};
export const isMedia = (path: string) => /\.(mp4|m4v|webm|mkv|mov|ogv|mp3|ogg|opus|flac|wav|m4a|aac)$/i.test(path);
export const isAudio = (path: string) => /\.(mp3|ogg|opus|flac|wav|m4a|aac)$/i.test(path);
