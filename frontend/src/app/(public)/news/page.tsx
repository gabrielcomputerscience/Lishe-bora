import { NewsCard } from "@/components/NewsCard";
import { publicGet } from "@/lib/server";
import type { NewsItem } from "@/lib/types";
import { PageBanner } from "@/components/PageBanner";

export const metadata = { title: "News" };
export default async function News() {
  const items = (await publicGet<NewsItem[]>("/news")) ?? [];
  return (
    <><PageBanner slot="page:news" eyebrow="News" title="News & updates" sub="Announcements, guides and stories from the programme." />
    <section className="wrap sec">
      {items.length ? <div className="grid g3" style={{ marginTop: 16 }}>{items.map((n) => <NewsCard key={n.slug} n={n} />)}</div>
        : <p className="muted">No news yet.</p>}
    </section></>
  );
}
