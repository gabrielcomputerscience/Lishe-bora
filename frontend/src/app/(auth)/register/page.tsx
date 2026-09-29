"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { AuthShell, RegisterAside } from "@/components/AuthShell";
import { DevCode, ErrorBox, Field, OtpInput } from "@/components/ui";
import { ApiError, get, post } from "@/lib/api";
import type { TokenOut } from "@/lib/types";
import type { FoodCategory } from "@/lib/types";

const TYPES = [
  ["farmer", "Individual farmer", "Sell your own produce"],
  ["cooperative", "Farmer group / cooperative", "Register the group and its members"],
  ["aggregator", "Aggregator", "Buy from farmers, grade and supply"],
  ["trader", "Trader / processor / MSME", "Registered business supplier"],
] as const;
const STEPS = ["Account type", "Details", "Inclusion", "Password", "Verify"];

type Form = {
  account_type: string; legal_name: string; contact_name: string; registration_no: string; kra_pin: string; phone: string;
  email: string; county_id: string; sub_county: string; commodities: string[]; members_count: string; sms_language: string;
  leadership: string; pct_women: string; pct_youth: string; inclusion_consent: boolean; password: string; password2: string; accept_terms: boolean;
};

function Register() {
  const router = useRouter();
  const qs = useSearchParams();
  const [step, setStep] = useState(1);
  const [counties, setCounties] = useState<{ id: string; name: string }[]>([]);
  const [foodCats, setFoodCats] = useState<FoodCategory[]>([]);
  const [f, setF] = useState<Form>({ account_type: "cooperative", legal_name: "", contact_name: "", registration_no: "", kra_pin: "", phone: "",
    email: "", county_id: "", sub_county: "", commodities: [], members_count: "", sms_language: "en", leadership: "prefer_not_to_say",
    pct_women: "", pct_youth: "", inclusion_consent: false, password: "", password2: "", accept_terms: false });
  const [reg, setReg] = useState<{ user_id: string; sent_to: string; dev_code?: string | null } | null>(null);
  const [code, setCode] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const [fe, setFe] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    get<{ id: string; name: string }[]>("/public/counties").then(setCounties).catch(() => {});
    get<FoodCategory[]>("/public/food-categories").then(setFoodCats).catch(() => {});
    const v = qs.get("verify");
    if (v) { setReg({ user_id: v, sent_to: "your phone" }); setStep(5); }
  }, [qs]);

  const set = (k: keyof Form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setF({ ...f, [k]: e.target.type === "checkbox" ? (e.target as HTMLInputElement).checked : e.target.value });
  const group = f.account_type === "cooperative";
  const next = () => { setErr(null); setStep(step + 1); };

  function validateDetails() {
    const e: Record<string, string> = {};
    if (f.legal_name.trim().length < 2) e.legal_name = "Required";
    if (f.contact_name.trim().length < 2) e.contact_name = "Required";
    if (!/^(\+?254|0)(7|1)\d{8}$/.test(f.phone.replace(/[\s-]/g, ""))) e.phone = "Enter a valid Kenyan mobile number";
    if (!f.county_id) e.county_id = "Choose a county";
    setFe(e); return !Object.keys(e).length;
  }

  async function submit() {
    setErr(null); setFe({});
    if (f.password !== f.password2) { setFe({ password2: "Passwords do not match" }); return; }
    setBusy(true);
    try {
      const r = await post<{ user_id: string; sent_to: string; dev_code?: string }>("/auth/register/supplier", {
        account_type: f.account_type, legal_name: f.legal_name, contact_name: f.contact_name, registration_no: f.registration_no,
        kra_pin: f.kra_pin, phone: f.phone, email: f.email || null, county_id: f.county_id, sub_county: f.sub_county,
        commodities: f.commodities, members_count: f.members_count ? Number(f.members_count) : null, sms_language: f.sms_language,
        inclusion: { leadership: f.leadership, pct_women: f.pct_women ? Number(f.pct_women) : null, pct_youth: f.pct_youth ? Number(f.pct_youth) : null },
        inclusion_consent: f.inclusion_consent, accept_terms: f.accept_terms, password: f.password,
      });
      setReg(r); setStep(5);
    } catch (e) {
      setErr(e);
      if (e instanceof ApiError) {
        const m = e.fieldErrors(); setFe(m);
        if (["legal_name", "phone", "county_id", "email"].some((k) => k in m) || e.code === "PHONE_IN_USE" || e.code === "EMAIL_IN_USE") setStep(2);
      }
    } finally { setBusy(false); }
  }

  async function verify(e: React.FormEvent) {
    e.preventDefault(); setErr(null); setBusy(true);
    try { await post("/auth/verify-phone", { user_id: reg?.user_id, code }); setStep(6); }
    catch (x) { setErr(x); } finally { setBusy(false); }
  }
  async function resend() {
    try { const r = await post<TokenOut>("/auth/register/resend", { user_id: reg?.user_id }); setReg({ ...reg!, dev_code: r.dev_code, sent_to: r.sent_to || reg!.sent_to }); }
    catch (x) { setErr(x); }
  }

  const bar = step <= 5 && <div className="steps" aria-label="Progress">{STEPS.map((s, i) =>
    <div key={s} className={`step ${i + 1 < step ? "done" : ""} ${i + 1 === step ? "cur" : ""}`}>{s}</div>)}</div>;
  const nav = (onNext: () => void, label = "Continue") => (
    <div className="row" style={{ marginTop: 8 }}>
      {step > 1 && <button type="button" className="btn" onClick={() => setStep(step - 1)}>Back</button>}
      <span className="spacer" /><button type="button" className="btn primary" disabled={busy} onClick={onNext}>{label}</button>
    </div>);

  return (
    <AuthShell aside={RegisterAside}>
      {step === 1 && (<><h1>Create a supplier account</h1><p className="muted">Which best describes you?</p>{bar}
        {TYPES.map(([k, t, d]) => <button key={k} type="button" className="roleopt" aria-pressed={f.account_type === k}
          onClick={() => setF({ ...f, account_type: k })}><b>{t}</b><span>{d}</span></button>)}
        <p className="small muted">Schools and county staff: your account is created by an administrator. <Link href="/sign-in">Sign in</Link></p>
        {nav(next)}</>)}

      {step === 2 && (<><h1>{group ? "Group details" : "Your details"}</h1>{bar}
        <Field label={group ? "Registered group name" : f.account_type === "farmer" ? "Full name" : "Business name"} id="ln" error={fe.legal_name}>
          <input id="ln" value={f.legal_name} onChange={set("legal_name")} /></Field>
        {f.account_type !== "farmer" && <Field label="Contact person" id="cn" error={fe.contact_name}><input id="cn" value={f.contact_name} onChange={set("contact_name")} /></Field>}
        <div className="grid g2">
          <Field label={group ? "Registration no." : "ID / registration no."} id="rn"><input id="rn" value={f.registration_no} onChange={set("registration_no")} /></Field>
          <Field label={`KRA PIN${f.account_type === "farmer" ? " (optional)" : ""}`} id="kp"><input id="kp" value={f.kra_pin} onChange={set("kra_pin")} /></Field>
        </div>
        <div className="grid g2">
          <Field label="Mobile number" id="ph" error={fe.phone}><input id="ph" inputMode="tel" value={f.phone} onChange={set("phone")} placeholder="07XX XXX XXX" /></Field>
          <Field label="Email (optional)" id="em" error={fe.email}><input id="em" type="email" value={f.email} onChange={set("email")} /></Field>
        </div>
        <div className="grid g2">
          <Field label="County" id="co" error={fe.county_id}><select id="co" value={f.county_id} onChange={set("county_id")}>
            <option value="">Choose…</option>{counties.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>
          <Field label="Sub-county / ward" id="sc"><input id="sc" value={f.sub_county} onChange={set("sub_county")} /></Field>
        </div>
        <Field label="Commodities you supply">{foodCats.filter((g) => g.commodities.length).map((g) => (
          <div key={g.key} className="stack" style={{ marginBottom: 8 }}><div className="small muted">{g.label}</div>
            <div className="chips">{g.commodities.map((c) => (
              <label key={c.code} className="chip"><input type="checkbox" checked={f.commodities.includes(c.code)}
                onChange={(e) => setF({ ...f, commodities: e.target.checked ? [...f.commodities, c.code] : f.commodities.filter((x) => x !== c.code) })} /> {c.name}</label>))}</div></div>))}</Field>
        {group && <Field label="Number of members" id="mc" hint="You can upload the member list later."><input id="mc" type="number" min={1} value={f.members_count} onChange={set("members_count")} /></Field>}
        <Field label="Preferred language for SMS" id="sl"><select id="sl" value={f.sms_language} onChange={set("sms_language")}><option value="en">English</option><option value="sw">Kiswahili</option></select></Field>
        <ErrorBox error={err} />
        {nav(() => { if (!f.contact_name && f.account_type === "farmer") f.contact_name = f.legal_name; if (validateDetails()) next(); })}</>)}

      {step === 3 && (<><h1>Inclusion information</h1>{bar}
        <p className="muted small">This helps the programme track fair access for women, youth and persons with disabilities. Some procurement criteria reward inclusion, and a county officer verifies your status before it counts.</p>
        <Field label={group ? "Who leads the group?" : "Ownership"} id="ld"><select id="ld" value={f.leadership} onChange={set("leadership")}>
          <option value="women">Women-led / majority women-owned</option><option value="youth">Youth-led (18–35)</option>
          <option value="pwd">Led by a person with disability</option><option value="none">None of these</option><option value="prefer_not_to_say">Prefer not to say</option></select></Field>
        {group && <div className="grid g2"><Field label="% women members" id="pw1"><input id="pw1" type="number" min={0} max={100} value={f.pct_women} onChange={set("pct_women")} /></Field>
          <Field label="% youth members" id="py"><input id="py" type="number" min={0} max={100} value={f.pct_youth} onChange={set("pct_youth")} /></Field></div>}
        <label className="chk"><input type="checkbox" checked={f.inclusion_consent} onChange={set("inclusion_consent")} />
          I consent to LisheBora processing this information for programme monitoring, as described in the <Link href="/p/privacy" target="_blank">privacy notice</Link> (Data Protection Act, 2019).</label>
        {nav(next)}</>)}

      {step === 4 && (<><h1>Set your password</h1>{bar}
        <Field label="Password" id="p1" error={fe.password} hint="At least 10 characters, with upper- and lower-case letters and a number.">
          <input id="p1" type="password" autoComplete="new-password" value={f.password} onChange={set("password")} /></Field>
        <Field label="Confirm password" id="p2" error={fe.password2}><input id="p2" type="password" autoComplete="new-password" value={f.password2} onChange={set("password2")} /></Field>
        <label className="chk"><input type="checkbox" checked={f.accept_terms} onChange={set("accept_terms")} />
          I accept the <Link href="/p/terms" target="_blank">terms of use</Link> and <Link href="/p/privacy" target="_blank">privacy notice</Link>.</label>
        <ErrorBox error={err} />
        {nav(submit, busy ? "Creating…" : "Create account")}</>)}

      {step === 5 && (<form onSubmit={verify}><h1>Verify your phone</h1>{bar}
        <p className="muted">Enter the 6-digit code we sent to {reg?.sent_to}.</p>
        <DevCode code={reg?.dev_code} />
        <OtpInput value={code} onChange={setCode} />
        <ErrorBox error={err} />
        <div className="row" style={{ marginTop: 14 }}><button type="button" className="btn" onClick={resend}>Resend code</button><span className="spacer" />
          <button className="btn primary" disabled={busy || code.length !== 6}>Verify</button></div></form>)}

      {step === 6 && (<><h1>Account created</h1>
        <p className="muted">Your application has been <b>submitted for prequalification</b>. Upload your documents so a county officer can review them. We will SMS you when you are approved.</p>
        <div className="steps">{["Submitted", "Under review", "Approved", "Prequalified"].map((s, i) =>
          <div key={s} className={`step ${i === 0 ? "done" : ""} ${i === 1 ? "cur" : ""}`}>{s}</div>)}</div>
        <button className="btn primary lg" onClick={() => router.push("/app/my-supplier")}>Upload documents</button></>)}
    </AuthShell>
  );
}

export default function RegisterPage() { return <Suspense><Register /></Suspense>; }
