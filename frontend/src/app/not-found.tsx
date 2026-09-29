import Link from "next/link";
export default function NotFound() {
  return <div className="wrap sec narrow"><h1>Page not found</h1><p className="muted">The page you are looking for does not exist or is not published.</p><Link className="btn primary" href="/">Go to homepage</Link></div>;
}
