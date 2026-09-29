"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { AuthShell, SignInAside } from "@/components/AuthShell";
import { DevCode, ErrorBox, Field, OtpInput } from "@/components/ui";
import { ApiError, post } from "@/lib/api";
import type { TokenOut } from "@/lib/types";

type Mode = "password" | "otp" | "mfa" | "otp-code";

export default function SignIn() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("password");
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [mfa, setMfa] = useState<TokenOut | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);

  const done = () => router.push("/app");
  async function run(fn: () => Promise<void>) {
    setErr(null); setIsAdmin(false); setBusy(true);
    try { await fn(); }
    catch (e) {
      if (e instanceof ApiError && e.code === "USE_ADMIN_SIGN_IN") setIsAdmin(true);
      if (e instanceof ApiError && e.code === "PHONE_NOT_VERIFIED") {
        const uid = e.details[0]?.user_id as string | undefined;
        if (uid) { router.push(`/register?verify=${uid}`); return; }
      }
      setErr(e);
    } finally { setBusy(false); }
  }
  const login = (e: React.FormEvent) => { e.preventDefault(); run(async () => {
    const r = await post<TokenOut>("/auth/login", { identifier, password });
    if (r.mfa_required) { setMfa(r); setCode(""); setMode("mfa"); } else done();
  }); };
  const verifyMfa = (e: React.FormEvent) => { e.preventDefault(); run(async () => {
    await post("/auth/mfa/verify", { mfa_token: mfa?.mfa_token, code }); done();
  }); };
  const requestOtp = (e: React.FormEvent) => { e.preventDefault(); run(async () => {
    const r = await post<TokenOut>("/auth/otp/request", { phone }); setMfa(r); setCode(""); setMode("otp-code");
  }); };
  const otpLogin = (e: React.FormEvent) => { e.preventDefault(); run(async () => { await post("/auth/otp/login", { phone, code }); done(); }); };

  return (
    <AuthShell aside={SignInAside}>
      {mode === "password" && (
        <form onSubmit={login} noValidate>
          <h1>Sign in</h1><p className="muted">Use your email or mobile number.</p>
          <Field label="Email or mobile number" id="id"><input id="id" autoComplete="username" value={identifier} onChange={(e) => setIdentifier(e.target.value)} placeholder="e.g. 0712 345 678" required /></Field>
          <Field label="Password" id="pw"><input id="pw" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></Field>
          <div className="row" style={{ justifyContent: "flex-end", marginBottom: 12 }}><Link className="small" href="/forgot-password">Forgot password?</Link></div>
          <ErrorBox error={err} />
          {isAdmin && <p className="small"><Link className="btn sm" href="/admin/sign-in">Go to the administrator sign-in →</Link></p>}
          <button className="btn primary lg block" disabled={busy}>Sign in</button>
          <div className="or">or</div>
          <button type="button" className="btn lg block" onClick={() => { setErr(null); setMode("otp"); }}>Sign in with a one-time SMS code</button>
          <p className="small" style={{ marginTop: 18 }}>New supplier? <Link href="/register">Create an account</Link></p>
        </form>)}
      {mode === "mfa" && (
        <form onSubmit={verifyMfa}>
          <h1>Verify it’s you</h1>
          <p className="muted">Enter the 6-digit code sent to {mfa?.sent_to}. Approval, procurement and finance roles use two-step verification.</p>
          <DevCode code={mfa?.dev_code} />
          <OtpInput value={code} onChange={setCode} />
          <ErrorBox error={err} />
          <button className="btn primary lg block" style={{ marginTop: 14 }} disabled={busy || code.length !== 6}>Verify</button>
          <p className="small muted"><button type="button" className="btn sm" onClick={() => setMode("password")}>← Start again</button></p>
        </form>)}
      {mode === "otp" && (
        <form onSubmit={requestOtp}>
          <h1>Sign in with SMS code</h1><p className="muted">We will send a 6-digit code to your registered phone.</p>
          <Field label="Mobile number" id="ph"><input id="ph" inputMode="tel" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="07XX XXX XXX" /></Field>
          <ErrorBox error={err} />
          <button className="btn primary lg block" disabled={busy}>Send code</button>
          <p className="small"><button type="button" className="btn sm" onClick={() => setMode("password")}>← Use password instead</button></p>
        </form>)}
      {mode === "otp-code" && (
        <form onSubmit={otpLogin}>
          <h1>Enter your code</h1><p className="muted">If {mfa?.sent_to} is registered, a code is on its way.</p>
          <DevCode code={mfa?.dev_code} />
          <OtpInput value={code} onChange={setCode} />
          <ErrorBox error={err} />
          <button className="btn primary lg block" style={{ marginTop: 14 }} disabled={busy || code.length !== 6}>Sign in</button>
        </form>)}
    </AuthShell>
  );
}
