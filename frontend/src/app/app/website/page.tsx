"use client";
import { useCallback, useEffect, useState } from "react";
import { ErrorBox, Field, PageHead, Pill, useToast } from "@/components/ui";
import { get, post, put } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { FlowButtons } from "@/components/CmsFlow";
import { WebsiteImages } from "@/components/WebsiteImages";
import { StyleControls } from "@/components/StyleControls";
import type { TextStyle } from "@/lib/textStyle";
import { fmtDateTime } from "@/lib/format";

type Block = { key: string; data: Record<string, unknown>; published_data: Record<string, unknown>; status: string; version: number; updated_at: string };
type News = { id: string; slug: string; title: string; category: string; summary: string; body: string; status: string; version: number; published_at: string | null; updated_at: string; review_note: string; cover_image: string; cover_alt: string; language: string };
type Pg = { id: string; slug: string; title: string; body: string; status: string; version: number; updated_at: string; show_in_nav: boolean; language: string };
type Faq = { id: string; question: string; answer: string; sort_order: number; is_published: boolean; language: string };
type Msg = { id: string; name: string; contact: string; topic: string; message: string; status: string; created_at: string };
type StatItem = { value: string; label: string };

export default function Website() {
  const { can } = useAuth();
  const c = (p: string) => can(p);
  const [tab, setTab] = useState("home");
  const [blocks, setBlocks] = useState<Block[]>([]);
  const [news, setNews] = useState<News[]>([]);
  const [pages, setPages] = useState<Pg[]>([]);
  const [faq, setFaq] = useState<Faq[]>([]);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [edit, setEdit] = useState<Partial<News> | null>(null);
  const [page, setPage] = useState<Partial<Pg> | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const { toast, node } = useToast();
  const load = useCallback(async () => {
    try {
      const [b, n, p, f] = await Promise.all([get<Block[]>("/cms/blocks"), get<News[]>("/cms/news"), get<Pg[]>("/cms/pages"), get<Faq[]>("/cms/faq")]);
      setBlocks(b); setNews(n); setPages(p); setFaq(f);
      get<Msg[]>("/cms/messages").then(setMsgs).catch(() => {});
    } catch (e) { setErr(e); }
  }, []);
  useEffect(() => { load(); }, [load]);
  const run = async (fn: () => Promise<unknown>, ok: string) => { setErr(null); try { await fn(); toast(ok); await load(); } catch (e) { setErr(e); } };

  const hero = blocks.find((b) => b.key === "hero");
  const stats = blocks.find((b) => b.key === "stats");
  const site = blocks.find((b) => b.key === "site");
  const heroData = (hero?.data ?? {}) as Record<string, string>;
  const statsData = (stats?.data ?? { show: false, items: [] }) as { show: boolean; show_live?: boolean; items: StatItem[]; styles?: Record<string, TextStyle> };
  const heroStyles = ((hero?.data ?? {}).styles ?? {}) as Record<string, TextStyle>;
  const setHeroStyle = (k: string, v: TextStyle | undefined) => setBlocks(blocks.map((b) => b.key === "hero"
    ? { ...b, data: { ...b.data, styles: Object.fromEntries(Object.entries({ ...heroStyles, [k]: v }).filter(([, x]) => x)) } } : b));
  const setStatStyle = (k: string, v: TextStyle | undefined) => setStats({ ...statsData,
    styles: Object.fromEntries(Object.entries({ ...(statsData.styles ?? {}), [k]: v }).filter(([, x]) => x)) as Record<string, TextStyle> });
  const setHero = (k: string, v: string) => setBlocks(blocks.map((b) => b.key === "hero" ? { ...b, data: { ...b.data, [k]: v } } : b));
  const setStats = (d: typeof statsData) => setBlocks(blocks.map((b) => b.key === "stats" ? { ...b, data: d } : b));

  return (
    <>
      <PageHead crumb="Administration › Website content" title="Public website" sub="Editors draft and submit for review. Approvers publish. Every change is versioned and audited.">
        <a className="btn" href="/" target="_blank">View website ↗</a>
      </PageHead>
      <div className="tabs">{[["home", "Homepage"], ["images", "Images & backgrounds"], ["news", "News & updates"], ["pages", "Pages"], ["faq", "FAQ"], ["messages", `Messages (${msgs.length})`]].map(([k, l]) =>
        <button key={k} className={`tab ${tab === k ? "on" : ""}`} onClick={() => setTab(k)}>{l}</button>)}</div>
      <ErrorBox error={err} />

      {tab === "home" && hero && stats && (<div className="grid g2" style={{ alignItems: "start" }}>
        <div className="card"><div className="row"><h3>Hero banner</h3><span className="spacer" /><Pill status={hero.status} /></div>
          {(["eyebrow", "title", "subtitle", "cta_label", "cta2_label"] as const).map((k) => (
            <Field key={k} label={{ eyebrow: "Eyebrow", title: "Headline", subtitle: "Introduction", cta_label: "First button (gold)", cta2_label: "Second button (outline)" }[k]}>
              <>{k === "subtitle" ? <textarea rows={3} value={heroData[k] ?? ""} onChange={(e) => setHero(k, e.target.value)} />
                : <input value={heroData[k] ?? ""} placeholder={{ cta_label: "Register as a supplier", cta2_label: "View open opportunities" }[k as string]} onChange={(e) => setHero(k, e.target.value)} />}
              {(k === "cta_label" || k === "cta2_label") && <div className="row" style={{ gap: 8, marginTop: 6 }}>
                <input style={{ flex: 1 }} aria-label="Button link" placeholder={k === "cta_label" ? "Link: /register" : "Link: /opportunities"}
                  value={heroData[k === "cta_label" ? "cta_link" : "cta2_link"] ?? ""} onChange={(e) => setHero(k === "cta_label" ? "cta_link" : "cta2_link", e.target.value)} />
                <label className="small"><input type="checkbox" checked={heroData[k === "cta_label" ? "cta_hidden" : "cta2_hidden"] !== "yes"}
                  onChange={(e) => setHero(k === "cta_label" ? "cta_hidden" : "cta2_hidden", e.target.checked ? "" : "yes")} /> Show</label></div>}
              <StyleControls value={heroStyles[k]} onChange={(v) => setHeroStyle(k, v)} preview={heroData[k] ?? ({ cta_label: "Register as a supplier", cta2_label: "View open opportunities" }[k as string] ?? "")}
                dark={!k.startsWith("cta")} button={k === "cta_label" ? "gold" : k === "cta2_label" ? "ghost" : undefined}
                defaultSize={{ eyebrow: 13, title: 44, subtitle: 18, cta_label: 16, cta2_label: 16 }[k]} /></></Field>))}
          <p className="small muted">Links: a page on this site (e.g. /opportunities, /p/for-suppliers) or a full https:// address.</p>
          <div className="row"><button className="btn" disabled={!c("cms:edit")} onClick={() => run(() => put("/cms/blocks/hero", { data: hero.data }), "Draft saved")}>Save draft</button>
            <FlowButtons republish status={hero.status} can={c} onAct={(a) => run(async () => { if (a !== "unpublish") await put("/cms/blocks/hero", { data: hero.data }); await post("/cms/blocks/hero/workflow", { action: a }); }, `Hero: ${a}`)} /></div>
          <p className="small muted">Version {hero.version} · updated {fmtDateTime(hero.updated_at)}</p></div>
        <div className="card"><div className="row"><h3>Programme at a glance</h3><span className="spacer" /><Pill status={stats.status} /></div>
          <label className="chk" style={{ margin: "8px 0 12px" }}><input type="checkbox" checked={statsData.show_live !== false} onChange={(e) => setStats({ ...statsData, show_live: e.target.checked })} /> Show live platform figures (schools, counties, approved suppliers, foods, open opportunities: counted automatically)</label>
          <label className="chk" style={{ margin: "0 0 12px" }}><input type="checkbox" checked={statsData.show} onChange={(e) => setStats({ ...statsData, show: e.target.checked })} /> Show programme statistics below (typed in here)</label>
          {statsData.items.map((s, i) => (<div key={i} className="grid" style={{ gridTemplateColumns: "90px 1fr", gap: 8 }}>
            <Field label="Value"><input value={s.value} onChange={(e) => setStats({ ...statsData, items: statsData.items.map((x, j) => j === i ? { ...x, value: e.target.value } : x) })} /></Field>
            <Field label="Label"><input value={s.label} onChange={(e) => setStats({ ...statsData, items: statsData.items.map((x, j) => j === i ? { ...x, label: e.target.value } : x) })} /></Field></div>))}
          <Field label="Style of the values (applies to all)"><StyleControls value={statsData.styles?.value} onChange={(v) => setStatStyle("value", v)} preview={statsData.items[0]?.value ?? "200"} defaultSize={30} /></Field>
          <Field label="Style of the labels (applies to all)"><StyleControls value={statsData.styles?.label} onChange={(v) => setStatStyle("label", v)} preview={statsData.items[0]?.label ?? "schools in the pilot"} defaultSize={14} /></Field>
          <div className="alert warn small">Only publish figures that come from signed-off MEAL data. Never type in unverified numbers.</div>
          <div className="row"><button className="btn" disabled={!c("cms:edit")} onClick={() => run(() => put("/cms/blocks/stats", { data: statsData }), "Draft saved")}>Save draft</button>
            <FlowButtons republish status={stats.status} can={c} onAct={(a) => run(async () => { if (a !== "unpublish") await put("/cms/blocks/stats", { data: statsData }); await post("/cms/blocks/stats/workflow", { action: a }); }, `Statistics: ${a}`)} /></div></div>
      </div>)}
      {tab === "home" && site && (<div className="card" style={{ marginTop: 16 }}><div className="row"><h3>Contact details (footer and sign-in pages)</h3><span className="spacer" /><Pill status={site.status} /></div>
        <p className="small muted">Shown in the website footer and on the sign-in and registration pages. Leave a field empty to hide it.</p>
        <div className="grid g3">{([["phone", "Helpdesk phone"], ["sms_code", "SMS short code"], ["whatsapp", "WhatsApp"], ["email", "Helpdesk email"], ["address", "Office address"], ["hours", "Opening hours"], ["languages", "Languages"]] as const).map(([k, l]) => (
          <Field key={k} label={l}><input value={String((site.data as Record<string, string>)[k] ?? "")} onChange={(e) => setBlocks(blocks.map((b) => b.key === "site" ? { ...b, data: { ...b.data, [k]: e.target.value } } : b))} /></Field>))}</div>
        <div className="row"><button className="btn" disabled={!c("cms:edit")} onClick={() => run(() => put("/cms/blocks/site", { data: site.data }), "Draft saved")}>Save draft</button>
          <FlowButtons republish status={site.status} can={c} onAct={(a) => run(async () => { if (a !== "unpublish") await put("/cms/blocks/site", { data: site.data }); await post("/cms/blocks/site/workflow", { action: a }); }, `Contact details: ${a}`)} /></div>
      </div>)}

      {tab === "images" && <WebsiteImages block={blocks.find((b) => b.key === "backgrounds")} can={c} onChanged={load} />}

      {tab === "news" && (<div className="grid" style={{ gridTemplateColumns: "3fr 2fr", alignItems: "start" }}>
        <div className="card"><div className="row" style={{ marginBottom: 10 }}><h3>Posts</h3><span className="spacer" />
          {c("cms:create") && <button className="btn sm primary" onClick={() => setEdit({ title: "", category: "Announcement", summary: "", body: "" })}>+ New post</button>}</div>
          <div className="tablewrap"><table><thead><tr><th>Title</th><th>Category</th><th>Updated</th><th>Status</th><th /></tr></thead>
            <tbody>{news.map((n) => <tr key={n.id}><td><b>{n.title}</b>{n.review_note && <div className="small" style={{ color: "var(--gold-700)" }}>Note: {n.review_note}</div>}</td>
              <td>{n.category}</td><td className="small">{fmtDateTime(n.updated_at)}</td><td><Pill status={n.status} /></td>
              <td className="r"><div className="row" style={{ justifyContent: "flex-end", gap: 6 }}><button className="btn sm" onClick={() => setEdit(n)}>Edit</button>
                <FlowButtons status={n.status} can={c} onAct={(a) => run(() => post(`/cms/news/${n.id}/workflow`, { action: a }), `Post: ${a}`)} /></div></td></tr>)}</tbody></table></div></div>
        {edit && <div className="card"><h3>{edit.id ? "Edit post" : "New post"}</h3>
          <Field label="Title"><input value={edit.title ?? ""} onChange={(e) => setEdit({ ...edit, title: e.target.value })} /></Field>
          <Field label="Category"><select value={edit.category} onChange={(e) => setEdit({ ...edit, category: e.target.value })}>{["Announcement", "Guide", "Event", "Story"].map((x) => <option key={x}>{x}</option>)}</select></Field>
          <Field label="Summary"><textarea rows={2} value={edit.summary ?? ""} onChange={(e) => setEdit({ ...edit, summary: e.target.value })} /></Field>
          <Field label="Body (Markdown)" hint="Use ## for headings, **bold**, - for bullet lists."><textarea rows={10} value={edit.body ?? ""} onChange={(e) => setEdit({ ...edit, body: e.target.value })} /></Field>
          <Field label="Language"><select value={edit.language ?? "en"} onChange={(e) => setEdit({ ...edit, language: e.target.value })}><option value="en">English</option><option value="sw">Kiswahili</option></select></Field>
          <div className="row"><button className="btn primary" onClick={() => run(async () => {
              const body = { title: edit.title, category: edit.category, summary: edit.summary, body: edit.body, language: edit.language ?? "en", cover_image: edit.cover_image ?? "", cover_alt: edit.cover_alt ?? "" };
              if (edit.id) await put(`/cms/news/${edit.id}`, body); else await post("/cms/news", body); setEdit(null); }, "Post saved as draft")}>Save</button>
            <button className="btn" onClick={() => setEdit(null)}>Cancel</button></div></div>}
      </div>)}

      {tab === "pages" && (<div className="grid" style={{ gridTemplateColumns: "2fr 3fr", alignItems: "start" }}>
        <div className="card"><div className="row" style={{ marginBottom: 10 }}><h3>Pages</h3><span className="spacer" />
          {c("cms:create") && <button className="btn sm primary" onClick={() => setPage({ slug: "", title: "", body: "" })}>+ New page</button>}</div>
          {pages.map((p) => <div key={p.id} className="row" style={{ padding: "8px 0", borderBottom: "1px solid var(--line)" }}>
            <div><b>{p.title}</b><div className="small muted">/{p.slug === "about" || p.slug === "how-it-works" ? p.slug : `p/${p.slug}`}</div></div><span className="spacer" />
            <Pill status={p.status} /><button className="btn sm" onClick={() => setPage(p)}>Edit</button></div>)}</div>
        {page && <div className="card"><h3>{page.id ? `Edit: ${page.title}` : "New page"}</h3>
          {!page.id && <Field label="Address (slug)" hint="e.g. grievance-procedure"><input value={page.slug ?? ""} onChange={(e) => setPage({ ...page, slug: e.target.value })} /></Field>}
          <Field label="Title"><input value={page.title ?? ""} onChange={(e) => setPage({ ...page, title: e.target.value })} /></Field>
          <Field label="Content (Markdown)"><textarea rows={14} value={page.body ?? ""} onChange={(e) => setPage({ ...page, body: e.target.value })} /></Field>
          <div className="row"><button className="btn primary" onClick={() => run(async () => {
              await put(`/cms/pages/${page.slug}`, { title: page.title, body: page.body, show_in_nav: page.show_in_nav ?? false, language: page.language ?? "en" }); setPage(null); }, "Page saved")}>Save</button>
            {page.id && page.status && <FlowButtons status={page.status} can={c} onAct={(a) => run(() => post(`/cms/pages/${page.slug}/workflow`, { action: a }), `Page: ${a}`)} />}
            <button className="btn" onClick={() => setPage(null)}>Cancel</button></div></div>}
      </div>)}

      {tab === "faq" && (<div className="card">
        {faq.map((f) => <FaqRow key={f.id} f={f} canEdit={c("cms:edit")} onSave={(b) => run(() => put(`/cms/faq/${f.id}`, b), "Question saved")} />)}
        {c("cms:create") && <button className="btn sm" onClick={() => run(() => post("/cms/faq", { question: "New question?", answer: "Answer", sort_order: faq.length, is_published: false }), "Question added")}>+ Add question</button>}
      </div>)}

      {tab === "messages" && (<div className="card"><div className="tablewrap"><table><thead><tr><th>Received</th><th>From</th><th>Topic</th><th>Message</th></tr></thead>
        <tbody>{msgs.map((m) => <tr key={m.id}><td className="small">{fmtDateTime(m.created_at)}</td><td><b>{m.name}</b><div className="small muted">{m.contact}</div></td>
          <td>{m.topic}</td><td className="small">{m.message}</td></tr>)}{!msgs.length && <tr><td colSpan={4} className="muted">No messages yet.</td></tr>}</tbody></table></div></div>)}
      {node}
    </>
  );
}

function FaqRow({ f, canEdit, onSave }: { f: Faq; canEdit: boolean; onSave: (b: Omit<Faq, "id">) => void }) {
  const [q, setQ] = useState(f.question); const [a, setA] = useState(f.answer); const [pub, setPub] = useState(f.is_published);
  return (<div style={{ padding: "12px 0", borderBottom: "1px solid var(--line)" }}>
    <Field label="Question"><input value={q} onChange={(e) => setQ(e.target.value)} disabled={!canEdit} /></Field>
    <Field label="Answer"><textarea rows={2} value={a} onChange={(e) => setA(e.target.value)} disabled={!canEdit} /></Field>
    <div className="row"><label className="small"><input type="checkbox" checked={pub} onChange={(e) => setPub(e.target.checked)} disabled={!canEdit} /> Published</label>
      {canEdit && <button className="btn sm" onClick={() => onSave({ question: q, answer: a, is_published: pub, sort_order: f.sort_order, language: f.language })}>Save</button>}</div>
  </div>);
}
