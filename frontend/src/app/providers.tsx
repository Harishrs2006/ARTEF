"use client";

import { ThemeProvider } from "next-themes";
import { ReactNode, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
// Installs the global window error / unhandledrejection listeners. The
// module was never imported before, so the error reporting it implements
// was dead code.
import "./error-handler";

export function Providers({ children }: { children: ReactNode }) {
  const router = useRouter();
  const { fetchUser, isAuthenticated, isLoading, accessToken, status, restoreSession } = useAuth();

  useEffect(() => {
    // Validate the persisted session once on boot. Until this resolves the
    // status is "unknown" and the auth guards keep the protected pages in
    // their loading state instead of flashing the login page.
    void restoreSession();
  }, [restoreSession]);

  useEffect(() => {
    if (accessToken && !isAuthenticated && !isLoading && status === "unknown") {
      fetchUser();
    }
  }, [fetchUser, isAuthenticated, isLoading, accessToken, status]);

  useEffect(() => {
    // The session can die while the user is on a protected page (an expired
    // access token, a revoked refresh token). When that happens the store is
    // cleared, and the user is sent to the login page with the current
    // location preserved so they can pick up where they left off.
    if (status === "unauthenticated" && typeof window !== "undefined") {
      const onAuthPage =
        window.location.pathname === "/login" || window.location.pathname === "/";
      if (!onAuthPage) {
        const next = encodeURIComponent(window.location.pathname || "/dashboard");
        router.replace(`/login?next=${next}`);
      }
    }
  }, [status, router]);

  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      {children}
    </ThemeProvider>
  );
}
