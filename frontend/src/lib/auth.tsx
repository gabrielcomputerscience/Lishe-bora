"use client";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { ApiError, get, post } from "./api";
import type { Me } from "./types";

type Ctx = { me: Me | null; loading: boolean; reload: () => Promise<void>; signOut: () => Promise<void>; can: (...perms: string[]) => boolean };
const AuthCtx = createContext<Ctx>({ me: null, loading: true, reload: async () => {}, signOut: async () => {}, can: () => false });

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const reload = useCallback(async () => {
    try { setMe(await get<Me>("/auth/me")); }
    catch (e) { if (e instanceof ApiError && e.status === 401) setMe(null); else throw e; }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { reload(); }, [reload]);
  const signOut = async () => { try { await post("/auth/logout"); } catch { /* already signed out */ } };
  const can = (...perms: string[]) => !!me && perms.some((p) => me.permissions.includes(p));
  return <AuthCtx.Provider value={{ me, loading, reload, signOut, can }}>{children}</AuthCtx.Provider>;
}
export const useAuth = () => useContext(AuthCtx);
