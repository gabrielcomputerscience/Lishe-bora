// Always render with the latest published CMS content (changes appear as soon as an approver publishes).
export const dynamic = "force-dynamic";

import { PublicFooter } from "@/components/PublicFooter";
import { PublicHeader } from "@/components/PublicHeader";

export default function PublicLayout({ children }: { children: React.ReactNode }) {
  return (<><PublicHeader /><main id="main">{children}</main><PublicFooter /></>);
}
