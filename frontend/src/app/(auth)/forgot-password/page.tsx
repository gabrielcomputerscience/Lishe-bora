"use client";
import Link from "next/link";
import { useState } from "react";
import { AuthShell, SignInAside } from "@/components/AuthShell";
import { DevCode, ErrorBox, Field, OtpInput } from "@/components/ui";
import { post } from "@/lib/api";
import type { TokenOut } from "@/lib/types";

export default function Forgot() {
  const [step, setStep] = useState(1);
  const [identifier, setIdentifier] = useState("");
  const [code, setCode] = useState("");
  const [pw, setPw] = useState("");
  const [sent, setSent] = useState<TokenOut | null>(null);
  const [err, setErr] = useState<unknown>(null);
  return (
    <AuthShell aside={SignInAside}>
      <h1>Reset your password</h1>
      {step === 1 && (<form onSubmit={async (e) => { e.preventDefault(); setErr(null);
          try { setSent(await post<TokenOut>("/auth/password/forgot", { identifier })); setStep(2); } catch (x) { setErr(x); } }}>
        <p className="muted">Enter your email or mobile number. We will send you a reset code.</p>
        <Field label="Email or mobile number" id="i"><input id="i" value={identifier} onChange={(e) => setIdentifier(e.target.value)} /></Field>
        <ErrorBox error={err} /><button className="btn primary lg block">Send reset code</button></form>)}
      {step === 2 && (<form onSubmit={async (e) => { e.preventDefault(); setErr(null);
          try { await post("/auth/password/reset", { identifier, code, new_password: pw }); setStep(3); } catch (x) { setErr(x); } }}>
        <p className="muted">If the account exists, a code was sent to {sent?.sent_to}.</p>
        <DevCode code={sent?.dev_code} />
        <OtpInput value={code} onChange={setCode} />
        <div style={{ height: 12 }} />
        <Field label="New password" id="p" hint="At least 10 characters, with upper- and lower-case letters and a number.">
          <input id="p" type="password" autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} /></Field>
        <ErrorBox error={err} /><button className="btn primary lg block" disabled={code.length !== 6}>Set new password</button></form>)}
      {step === 3 && (<><div className="alert info">Password updated. You have been signed out on all devices.</div><Link className="btn primary" href="/sign-in">Sign in</Link></>)}
    </AuthShell>
  );
}
