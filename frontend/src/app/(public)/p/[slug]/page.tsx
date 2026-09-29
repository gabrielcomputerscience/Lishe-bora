import { CmsPage } from "@/components/CmsPage";
export default async function Generic({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return <CmsPage slug={slug} />;
}
