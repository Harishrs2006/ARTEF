"use client";

import { ThemeProvider } from "next-themes";
import { ReactNode, useEffect } from "react";
import { useAuth } from "@/lib/auth";

export function Providers({ children }: { children: ReactNode }) {
  const { fetchUser, isAuthenticated, isLoading, accessToken, initializeAuth } = useAuth();

  useEffect(() => {
    initializeAuth();
  }, [initializeAuth]);

  useEffect(() => {
    if (accessToken && !isAuthenticated && !isLoading) {
      fetchUser();
    }
  }, [fetchUser, isAuthenticated, isLoading, accessToken]);

  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      {children}
    </ThemeProvider>
  );
}