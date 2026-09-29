import ReactMarkdown from "react-markdown";
// Raw HTML is not rendered (react-markdown default) — CMS content cannot inject scripts.
export function Markdown({ children }: { children: string }) {
  return <div className="prose"><ReactMarkdown>{children}</ReactMarkdown></div>;
}
