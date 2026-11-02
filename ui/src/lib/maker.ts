// Browser-side torrent creation. Files are hashed locally by create-torrent (MIT, webtorrent/create-torrent);
// nothing is uploaded unless the user explicitly chooses "Seed from this device".
import createTorrent, { isJunkPath } from "create-torrent";
import parseTorrent, { Parsed, toMagnetURI } from "parse-torrent";

/** A dropped/picked file plus the path it had inside a dropped folder ("/album/disc1/a.flac"). */
export type Picked = File & { fullPath?: string };

const parts = (f: Picked) => (f.fullPath ?? f.name).split("/").filter(Boolean);
export const isJunk = (f: Picked) => isJunkPath(parts(f));

function withPath(file: File, fullPath: string): Picked {
  Object.defineProperty(file, "fullPath", { value: fullPath, configurable: true });
  return file as Picked;
}

/** Files chosen with <input type=file> (webkitdirectory gives relative paths). */
export function fromInput(list: FileList): Picked[] {
  return Array.from(list).map((f) => withPath(f, f.webkitRelativePath ? "/" + f.webkitRelativePath : f.name));
}

async function walk(entry: FileSystemEntry, out: Picked[]): Promise<void> {
  if (entry.isFile) {
    const file = await new Promise<File>((res, rej) => (entry as FileSystemFileEntry).file(res, rej));
    out.push(withPath(file, entry.fullPath));
    return;
  }
  const reader = (entry as FileSystemDirectoryEntry).createReader();
  for (;;) {
    // readEntries returns results in batches; an empty batch means done.
    const batch = await new Promise<FileSystemEntry[]>((res, rej) => reader.readEntries(res, rej));
    if (!batch.length) return;
    for (const e of batch) await walk(e, out);
  }
}

/** Files and folders from a drop event. Entries must be grabbed before the first await. */
export async function fromDrop(dt: DataTransfer): Promise<Picked[]> {
  const entries = Array.from(dt.items ?? [])
    .map((i) => (i.kind === "file" ? i.webkitGetAsEntry?.() : null))
    .filter((e): e is FileSystemEntry => !!e);
  if (!entries.length) return fromInput(dt.files);
  const out: Picked[] = [];
  for (const e of entries) await walk(e, out);
  return out;
}

export interface MakeOptions {
  name: string; comment: string; private: boolean; pieceLength: number; // 0 = automatic
  trackers: string[]; webSeeds: string[];
}
export interface Made { torrent: Uint8Array; parsed: Parsed; magnet: string; kept: Picked[] }

export const parseList = (text: string) => text.split(/\s+/).map((s) => s.trim()).filter(Boolean);

export function validateUrls(urls: string[], schemes: RegExp): string | null {
  const bad = urls.find((u) => !schemes.test(u));
  return bad ? `Not a valid URL: ${bad.slice(0, 60)}` : null;
}

export function suggestName(files: Picked[]): string {
  const first = files[0] && parts(files[0]);
  if (!first) return "";
  if (files.length === 1) return first[first.length - 1];
  return first.length > 1 && files.every((f) => parts(f)[0] === first[0]) ? first[0] : "my-files";
}

export async function make(files: Picked[], o: MakeOptions, onProgress: (done: number, total: number) => void): Promise<Made> {
  const kept = files.filter((f) => !isJunk(f));
  if (!kept.length) throw new Error("Nothing to share: all selected files are hidden system files.");
  const opts: Record<string, unknown> = {
    name: o.name || undefined, createdBy: "swarm", private: o.private || undefined,
    comment: o.comment || undefined, pieceLength: o.pieceLength || undefined,
    // An explicit (possibly empty) list stops the library adding its eight built-in public trackers.
    announceList: o.trackers.map((t) => [t]),
    urlList: o.webSeeds.length ? o.webSeeds : undefined,
    onProgress,
  };
  const torrent = await new Promise<Uint8Array>((res, rej) =>
    createTorrent(files, opts, (err, t) => (err || !t ? rej(err ?? new Error("no output")) : res(t))));
  const parsed = await parseTorrent(torrent);
  return { torrent, parsed, magnet: toMagnetURI({ infoHash: parsed.infoHash, name: parsed.name, announce: parsed.announce, urlList: parsed.urlList }), kept };
}

/** Understand a pasted magnet link / info hash or a dropped .torrent file. */
export async function inspect(input: string | Uint8Array): Promise<Made | { parsed: Parsed; magnet: string; torrent?: undefined }> {
  const parsed = await parseTorrent(input);
  const magnet = toMagnetURI({ infoHash: parsed.infoHash, name: parsed.name, announce: parsed.announce, urlList: parsed.urlList });
  return typeof input === "string" ? { parsed, magnet } : { torrent: input, parsed, magnet, kept: [] };
}

export const toBase64 = (b: Uint8Array) => {
  let s = "";
  for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode(...b.subarray(i, i + 0x8000));
  return btoa(s);
};

export function downloadBlob(data: Uint8Array, filename: string) {
  const url = URL.createObjectURL(new Blob([data as BlobPart], { type: "application/x-bittorrent" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}
