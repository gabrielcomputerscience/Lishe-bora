"use client";
import { useEffect, useState } from "react";
import { pillClass, human } from "@/lib/format";

export function Pill({ status, label }: { status: string; label?: string }) {
  return <span className={`pill ${pillClass(status)}`}>{label ?? human(status)}</span>;
}

export function Field({ label, error, hint, children, id }: { label: string; error?: string; hint?: string; children: React.ReactNode; id?: string }) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {children}
      {hint && !error && <span className="hint">{hint}</span>}
      {error && <span className="err" role="alert">{error}</span>}
    </div>
  );
}

export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  const msg = error instanceof Error ? error.message : String(error);
  return <div className="alert bad" role="alert">{msg}</div>;
}

export function PageHead({ crumb, title, sub, children }: { crumb?: string; title: string; sub?: string; children?: React.ReactNode }) {
  return (
    <>
      {crumb && <div className="crumb">{crumb}</div>}
      <div className="pagehead">
        <div><h1>{title}</h1>{sub && <div className="sub">{sub}</div>}</div>
        <div className="spacer" />
        <div className="row">{children}</div>
      </div>
    </>
  );
}

export function OtpInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <input className="otpone" inputMode="numeric" autoComplete="one-time-code" maxLength={6} pattern="\d{6}"
           aria-label="6-digit code" value={value} onChange={(e) => onChange(e.target.value.replace(/\D/g, "").slice(0, 6))}
           style={{ letterSpacing: "0.5em", fontSize: 22, textAlign: "center", padding: "10px", border: "1px solid #D0D5C6", borderRadius: 8, width: "100%" }} />
  );
}

export function useToast() {
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => { if (!msg) return; const t = setTimeout(() => setMsg(null), 3000); return () => clearTimeout(t); }, [msg]);
  return { toast: setMsg, node: msg ? <div className="toast" role="status">{msg}</div> : null };
}

export function DevCode({ code }: { code?: string | null }) {
  if (!code) return null;
  return <div className="alert warn small">Development mode: your code is <b>{code}</b> (SMS gateway not connected).</div>;
}
