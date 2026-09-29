"use client";
import { AppShell } from "@/components/AppShell";
import { AuthProvider } from "@/lib/auth";

export default function PortalLayout({ children }: { children: React.ReactNode }) {
  return <AuthProvider><AppShell>{children}</AppShell></AuthProvider>;
}
