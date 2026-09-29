// Server-side fetch for public pages (runs in the Next.js server, talks to FastAPI directly).
import "server-only";

const BACKEND = process.env.BACKEND_URL || "http://localhost:8000";

export async function publicGet<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${BACKEND}/api/v1/public${path}`, { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null; // backend offline — pages render a friendly empty state
  }
}
