"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Logo, Vein } from "./Brand";

export function AuthShell({ children, aside, admin }: { children: React.ReactNode; aside: React.ReactNode; admin?: boolean }) {
  return (
    <div className={`auth${admin ? " admin" : ""}`}>
      <div className="l">
        <Link href="/" aria-label="Back to website"><Logo tagline /></Link>
        {admin && <div className="adminbadge" style={{ marginTop: 14, alignSelf: "flex-start" }}>Administration</div>}
        <div className="form">{children}</div>
        <div className="small muted"><Link href="/">← Back to website</Link> · <Link href="/p/privacy">Privacy</Link></div>
      </div>
      <div className="r"><Vein /><div className="panel">{aside}</div></div>
    </div>
  );
}

export const SignInAside = (
  <><h2>Welcome to LisheBora</h2>
    <ul className="ticks"><li>Suppliers: find opportunities, bid and track payments</li><li>Schools: plan demand and confirm deliveries</li><li>Counties: approve, monitor and report</li></ul>
    <div className="alert info">Staff and school accounts are created by invitation. Suppliers can self-register.</div></>
);
export const AdminAside = (
  <><h2>Administration</h2>
    <p className="muted small">For Super Administrators and Administrators only. Administrator accounts cannot sign in on the main page,
      and staff, school and supplier accounts cannot sign in here.</p>
    <ul className="ticks"><li>Website content and publishing</li><li>Counties, schools, commodities and food categories</li><li>Users, onboarding imports and system health</li></ul>
    <div className="alert warn">Two-step verification is always required. Every sign-in and change is recorded in the audit trail.</div></>
);
export const RegisterAside = (
  <><h2>Need help registering?</h2>
    <p className="muted small">Assisted registration is available through county officers, aggregators and the helpdesk, and a group can register all its members in one go.</p>
    <ul className="ticks"><li>Takes about 10 minutes</li><li>SMS alerts for new opportunities</li><li>Upload documents now or later</li></ul>
    <Helpdesk /></>
);

/** Helpdesk line from Website content → Contact details (hidden until the programme team fills it in). */
function Helpdesk() {
  const [s, setS] = useState<{ phone?: string; sms_code?: string; email?: string } | null>(null);
  useEffect(() => { fetch("/api/v1/public/site").then((r) => r.json()).then(setS).catch(() => {}); }, []);
  const parts = [s?.phone, s?.sms_code && `SMS ${s.sms_code}`, s?.email].filter(Boolean);
  return parts.length ? <div className="alert info">Helpdesk: {parts.join(" · ")}</div> : null;
}
