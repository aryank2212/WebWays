// Neither package ships types; these cover only what we call.
declare module "create-torrent" {
  type Done = (err: Error | null, torrent?: Uint8Array) => void;
  export default function createTorrent(input: unknown, opts: Record<string, unknown>, cb: Done): void;
  export function isJunkPath(path: string[]): boolean;
}
declare module "parse-torrent" {
  export interface Parsed {
    infoHash: string; name?: string; length?: number; announce?: string[]; urlList?: string[]; private?: boolean;
    files?: { path: string; name: string; length: number; offset: number }[];
  }
  export default function parseTorrent(id: string | Uint8Array): Promise<Parsed> | Parsed;
  export function toMagnetURI(p: Partial<Parsed>): string;
}
