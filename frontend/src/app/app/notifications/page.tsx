"use client";
import Link from "next/link";
import { useAuth } from "@/lib/auth";
import { inMenu } from "@/lib/menu";
import { useCallback, useEffect, useState } from "react";
import { PageHead } from "@/components/ui";
import { get, post } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";

type N = { id: string; title: string; body: string; link: string; created_at: string; read: boolean };
export default function Notifications() {
  const { me, can } = useAuth();
  const [d, setD] = useState<{ unread: number; items: N[] } | null>(null);
  const load = useCallback(() => get<{ unread: number; items: N[] }>("/notifications").then(setD).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);
  return (
    <>
      <PageHead crumb="Account" title="Notifications" sub={d ? `${d.unread} unread` : ""}>
        <button className="btn" onClick={async () => { await post("/notifications/read"); load(); }}>Mark all as read</button>
      </PageHead>
      <div className="card">{d?.items.map((n) => (
        <div key={n.id} className="row" style={{ padding: "10px 0", borderBottom: "1px solid var(--line)", alignItems: "flex-start" }}>
          <span style={{ width: 8, height: 8, borderRadius: 4, marginTop: 7, background: n.read ? "transparent" : "var(--amber)" }} />
          <div style={{ flex: 1 }}><b>{n.title}</b><div className="small muted">{n.body}</div><div className="small muted">{fmtDateTime(n.created_at)}</div></div>
          {n.link && inMenu(me, can, n.link) && <Link className="btn sm" href={n.link} onClick={() => post("/notifications/read", [n.id])}>Open</Link>}
        </div>))}
        {d && !d.items.length && <p className="muted">No notifications yet.</p>}</div>
    </>
  );
}
