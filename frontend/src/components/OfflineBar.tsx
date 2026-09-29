"use client";
import { useState } from "react";
import { dropQueued, useOfflineQueue } from "@/lib/offline";
import { fmtDateTime } from "@/lib/format";

/** Connection status + records captured offline, with manual sync. */
export function OfflineBar({ onSynced }: { onSynced?: () => void }) {
  const { online, items, sync } = useOfflineQueue(onSynced);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  if (online && !items.length) return null;
  return (
    <div className={`alert ${online ? "info" : "warn"}`} style={{ marginBottom: 16 }} role="status">
      <div className="row">
        <b>{online ? "Online" : "You are offline"}</b>
        <span>{items.length ? `${items.length} record${items.length > 1 ? "s" : ""} saved on this device, waiting to sync.` : "Records you save will be kept on this device and sent when you reconnect."}</span>
        <span className="spacer" />
        {!!items.length && <button className="btn sm" onClick={() => setOpen(!open)}>{open ? "Hide" : "Show"}</button>}
        {online && !!items.length && <button className="btn sm primary" disabled={busy} onClick={async () => { setBusy(true); await sync(); setBusy(false); }}>{busy ? "Syncing…" : "Sync now"}</button>}
      </div>
      {open && <ul className="small" style={{ margin: "8px 0 0", paddingLeft: 18 }}>{items.map((q) => <li key={q.id}>{q.label} · {fmtDateTime(q.at)}
        {q.error && <> · <span style={{ color: "var(--red, #B3261E)" }}>{q.error}</span> <button className="btn sm ghost" onClick={() => dropQueued(q.id)}>Discard</button></>}</li>)}</ul>}
    </div>
  );
}
