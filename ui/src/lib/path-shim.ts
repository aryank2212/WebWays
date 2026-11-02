// Browser stand-in for Node's `path`, aliased in vite.config.ts. create-torrent and parse-torrent import it
// but only call join/sep/basename, and only with POSIX-style paths.
export const sep = "/";

export function join(...parts: string[]): string {
  const out: string[] = [];
  const absolute = parts.length > 0 && parts[0].startsWith("/");
  for (const seg of parts.join("/").split("/")) {
    if (seg === "" || seg === ".") continue;
    if (seg === "..") { if (out.length && out[out.length - 1] !== "..") out.pop(); else if (!absolute) out.push(".."); continue; }
    out.push(seg);
  }
  return (absolute ? "/" : "") + out.join("/") || (absolute ? "/" : ".");
}

export function basename(p: string): string {
  const trimmed = p.replace(/\/+$/, "");
  return trimmed.slice(trimmed.lastIndexOf("/") + 1);
}

export default { sep, join, basename };
