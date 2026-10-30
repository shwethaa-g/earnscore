import { createContext, useContext, useEffect, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Navigate, useLocation } from "react-router-dom";
import { api } from "../api/client";
import { FullPageLoading } from "../components/ui";

export type Role = "worker" | "officer" | "admin";
export type Me = {
  id: number;
  email: string;
  name: string;
  role: Role;
  preferred_language: "en" | "ta" | "hi";
  lender: { id: number; name: string } | null;
  profile: { city: string; work_type: string; languages: string[]; group_attr: string | null; group_attr_consent: boolean; training_consent: boolean } | null;
};

type Ctx = { me: Me | null | undefined; loading: boolean; refresh: () => Promise<void>; logout: () => Promise<void> };
const AuthCtx = createContext<Ctx>({ me: undefined, loading: true, refresh: async () => {}, logout: async () => {} });

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const q = useQuery<Me | null>({
    queryKey: ["me"],
    queryFn: async () => {
      const r = await api<{ user: Me | null }>("/auth/session");
      return r.user;
    },
    staleTime: 60_000,
    retry: false,
  });
  useEffect(() => {
    // any 401 from the API means the session ended: drop the user so guarded pages send them to sign in
    const onUnauthorized = () => qc.setQueryData(["me"], null);
    window.addEventListener("es:unauthorized", onUnauthorized);
    return () => window.removeEventListener("es:unauthorized", onUnauthorized);
  }, [qc]);
  const value: Ctx = {
    me: q.data,
    loading: q.isLoading,
    refresh: async () => {
      await qc.invalidateQueries({ queryKey: ["me"] });
    },
    logout: async () => {
      try {
        await api("/auth/logout", { method: "POST" });
      } finally {
        qc.setQueryData(["me"], null);
        qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" });
      }
    },
  };
  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export const useAuth = () => useContext(AuthCtx);

export const HOME: Record<Role, string> = { worker: "/worker", officer: "/officer", admin: "/admin" };

export function RequireRole({ role, children }: { role: Role; children: ReactNode }) {
  const { me, loading } = useAuth();
  const loc = useLocation();
  if (loading) return <FullPageLoading />;
  if (!me) return <Navigate to={`/login?next=${encodeURIComponent(loc.pathname)}`} replace />;
  if (me.role !== role) return <Navigate to={HOME[me.role]} replace />;
  return <>{children}</>;
}
