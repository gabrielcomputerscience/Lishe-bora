import Link from "next/link";
import { notFound } from "next/navigation";
import { Markdown } from "@/components/Markdown";
import { fmtDate } from "@/lib/format";
import { publicGet } from "@/lib/server";
import type { NewsItem } from "@/lib/types";

export default async function Article({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const n = await publicGet<NewsItem>(`/news/${slug}`);
  if (!n) notFound();
  return (
    <section className="wrap sec narrow">
      <Link href="/news">← News</Link>
      <div className="small muted" style={{ marginTop: 14 }}>{n.category} · {fmtDate(n.published_at)}</div>
      <h1 style={{ marginTop: 6 }}>{n.title}</h1>
      <p className="lead">{n.summary}</p>
      {n.body && <Markdown>{n.body}</Markdown>}
    </section>
  );
}
