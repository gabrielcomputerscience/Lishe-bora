"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { PageHead } from "@/components/ui";
import { get } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type Status = { counts: { users: number; schools: number }; outbox: { failed: number; queued: number } };
type News = { status: string };

/** Administration console: the landing page for Super Administrators and Administrators. */
export default function AdminConsole() {
  const { me, can } = useAuth();
  const [st, setSt] = useState<Status | null>(null);
  const [comms, setComms] = useState<number | null>(null);
  const [review, setReview] = useState<number | null>(null);
  useEffect(() => {
    if (can("iam:edit", "md:edit")) get<Status>("/system/status").then(setSt).catch(() => {});
    if (can("md:view")) get<unknown[]>("/commodities").then((r) => setComms(r.length)).catch(() => {});
    if (can("cms:view")) get<News[]>("/cms/news").then((r) => setReview(r.filter((n) => n.status === "in_review").length)).catch(() => {});
  }, [can]);
  if (!me) return null;
  const cards: { href: string; title: string; text: string; n?: number | null; show: boolean }[] = [
    { href: "/app/readiness", title: "Pilot readiness", text: "Checklist of what is still needed before the pilot: data, people, settings and website.", show: can("iam:edit", "md:edit") },
    { href: "/app/website", title: "Website content", text: "Home page, news, pages, FAQs and downloads. Write, review and publish.", n: review, show: can("cms:view") },
    { href: "/app/master-data", title: "Master data", text: "Counties, sub-counties and schools; commodities by food category; reference prices.", n: comms, show: can("md:edit") },
    { href: "/app/menus", title: "Menus & school terms", text: "Standard menus and the term calendar used for demand planning.", show: can("md:edit") },
    { href: "/app/users", title: "Users & roles", text: me.is_super_admin ? "All accounts, including administrators." : "Staff and school accounts. Administrator accounts are managed by the Super Administrator.", n: st?.counts.users, show: can("iam:view") },
    { href: "/app/system", title: "System & onboarding", text: "Import schools and staff, background jobs, messages that could not be sent.", n: st ? st.outbox.failed : null, show: can("iam:edit", "md:edit") },
    { href: "/app/audit", title: "Audit trail", text: "Every sign-in, change, approval and payment, with who and when.", show: can("aud:view") },
  ];
  return (
    <>
      <PageHead crumb="Administration" title="Admin console" sub={`Signed in as ${me.is_super_admin ? "Super Administrator" : "Administrator"} · ${me.full_name}`} />
      <div className="admingrid">
        {cards.filter((c) => c.show).map((c) => (
          <Link key={c.href} href={c.href} className="card">
            <h3>{c.title}</h3>
            {c.n !== undefined && c.n !== null && <div className="n">{c.n}<span className="small muted" style={{ fontFamily: "inherit", fontWeight: 400 }}>
              {c.href === "/app/website" ? " awaiting review" : c.href === "/app/system" ? " failed messages" : c.href === "/app/users" ? " accounts" : " commodities"}</span></div>}
            <p className="small muted">{c.text}</p>
          </Link>))}
      </div>
      <div className="card" style={{ marginTop: 16 }}>
        <h3>How administrator access works</h3>
        <ul className="small">
          <li>Administrator accounts sign in only at <b>/admin/sign-in</b>, always with a code. They cannot hold school, county, supplier or finance roles.</li>
          <li>Administrators manage all content: the public website, master data, users (except administrators) and onboarding. Operational records are read-only: administrators cannot approve, award or pay.</li>
          <li>Only the Super Administrator can create administrators or change their accounts.</li>
        </ul>
        {st && <p className="small muted">{st.counts.schools} schools · {st.outbox.queued} messages queued</p>}
      </div>
    </>
  );
}
