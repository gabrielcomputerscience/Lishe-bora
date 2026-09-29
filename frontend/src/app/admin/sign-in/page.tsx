"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { AdminAside, AuthShell } from "@/components/AuthShell";
import { DevCode, ErrorBox, Field, OtpInput } from "@/components/ui";
import { ApiError, post } from "@/lib/api";
import type { TokenOut } from "@/lib/types";

/** Administration sign-in: Super Administrators and Administrators only. Always two-step. */
export default function AdminSignIn() {
  const router = useRouter();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [mfa, setMfa] = useState<TokenOut | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const [notAdmin, setNotAdmin] = useState(false);
  const [busy, setBusy] = useState(false);

  async function run(fn: () => Promise<void>) {
    setErr(null); setNotAdmin(false); setBusy(true);
    try { await fn(); }
    catch (e) { if (e instanceof ApiError && e.code === "NOT_AN_ADMIN") setNotAdmin(true); setErr(e); }
    finally { setBusy(false); }
  }
  const login = (e: React.FormEvent) => { e.preventDefault(); run(async () => {
    const r = await post<TokenOut>("/auth/admin/login", { identifier, password }); setMfa(r); setCode("");
  }); };
  const verify = (e: React.FormEvent) => { e.preventDefault(); run(async () => {
    await post("/auth/mfa/verify", { mfa_token: mfa?.mfa_token, code }); router.push("/app/admin");
  }); };

  return (
    <AuthShell aside={AdminAside} admin>
      {!mfa ? (
        <form onSubmit={login} noValidate>
          <h1>Administrator sign-in</h1><p className="muted">Super Administrators and Administrators only.</p>
          <Field label="Email" id="aid"><input id="aid" autoComplete="username" value={identifier} onChange={(e) => setIdentifier(e.target.value)} required /></Field>
          <Field label="Password" id="apw"><input id="apw" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></Field>
          <div className="row" style={{ justifyContent: "flex-end", marginBottom: 12 }}><Link className="small" href="/forgot-password">Forgot password?</Link></div>
          <ErrorBox error={err} />
          {notAdmin && <p className="small"><Link className="btn sm" href="/sign-in">Go to the main sign-in →</Link></p>}
          <button className="btn primary lg block" disabled={busy}>Continue</button>
        </form>
      ) : (
        <form onSubmit={verify}>
          <h1>Verify it’s you</h1>
          <p className="muted">Enter the 6-digit code sent to {mfa.sent_to}.</p>
          <DevCode code={mfa.dev_code} />
          <OtpInput value={code} onChange={setCode} />
          <ErrorBox error={err} />
          <button className="btn primary lg block" style={{ marginTop: 14 }} disabled={busy || code.length !== 6}>Verify and sign in</button>
          <p className="small muted"><button type="button" className="btn sm" onClick={() => { setMfa(null); setErr(null); }}>← Start again</button></p>
        </form>
      )}
    </AuthShell>
  );
}
