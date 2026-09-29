import Link from "next/link";
import { fmtDate } from "@/lib/format";
import type { NewsItem } from "@/lib/types";
import { Vein } from "./Brand";

export function NewsCard({ n }: { n: NewsItem }) {
  return (
    <Link href={`/news/${n.slug}`} className="card newsc">
      <div className="thumb"><Vein stroke="#FFFFFF" className="" /></div>
      <div className="small muted">{n.category} · {fmtDate(n.published_at)}</div>
      <h3 style={{ margin: "6px 0" }}>{n.title}</h3>
      <p className="small muted" style={{ margin: 0 }}>{n.summary}</p>
    </Link>
  );
}
