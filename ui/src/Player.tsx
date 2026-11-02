import { isAudio } from "./api";

export interface PlayerTarget { title: string; url: string; path: string }

export default function Player({ target, onClose }: { target: PlayerTarget; onClose: () => void }) {
  const Tag = isAudio(target.path) ? "audio" : "video";
  return (
    <div className="modal" onClick={onClose}>
      <div className="modal-body" onClick={(e) => e.stopPropagation()}>
        <div className="row between">
          <strong>{target.title}</strong>
          <button onClick={onClose}>Close</button>
        </div>
        <Tag src={target.url} controls autoPlay className="player" />
        <p className="muted small">
          Playing straight from the swarm while it downloads. Not playing? Open this address in VLC or mpv:
          <br />
          <code>{new URL(target.url, location.href).href}</code>
        </p>
      </div>
    </div>
  );
}
