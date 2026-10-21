"use client";

import * as React from "react";
import { Sidebar } from "@/components/ui/sidebar";
import { Header } from "@/components/ui/header";
import { cn } from "@/lib/utils";

interface DashboardLayoutProps {
  children: React.ReactNode;
}

export const DashboardLayout: React.FC<DashboardLayoutProps> = ({ children }: DashboardLayoutProps) => {
  const [isSidebarCollapsed, setIsSidebarCollapsed] = React.useState(false);
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = React.useState(false);

  React.useEffect(() => {
    // The header dispatches these events; the mobile variant must be handled
    // separately from the desktop collapse toggle, otherwise the hamburger
    // button had no effect on small screens.
    const handleToggle = () => setIsSidebarCollapsed((prev) => !prev);
    const handleOpenMobile = () => setIsMobileSidebarOpen(true);
    const handleCloseMobile = () => setIsMobileSidebarOpen(false);

    document.addEventListener("toggle-sidebar", handleToggle);
    document.addEventListener("open-mobile-sidebar", handleOpenMobile);
    document.addEventListener("close-mobile-sidebar", handleCloseMobile);

    return () => {
      document.removeEventListener("toggle-sidebar", handleToggle);
      document.removeEventListener("open-mobile-sidebar", handleOpenMobile);
      document.removeEventListener("close-mobile-sidebar", handleCloseMobile);
    };
  }, []);

  return (
    <div className="min-h-screen bg-background">
      <Sidebar
        isCollapsed={isSidebarCollapsed}
        onToggle={() => setIsSidebarCollapsed((prev) => !prev)}
        isMobileOpen={isMobileSidebarOpen}
        onCloseMobile={() => setIsMobileSidebarOpen(false)}
      />
      <div
        className={cn(
          "transition-all duration-300 min-h-screen",
          isSidebarCollapsed ? "lg:ml-16" : "lg:ml-64"
        )}
      >
        <Header />
        <main className="p-4 lg:p-6">
          {children}
        </main>
      </div>
      <div
        className={cn(
          "fixed inset-0 z-40 bg-black/50 lg:hidden transition-opacity",
          isMobileSidebarOpen ? "opacity-100" : "opacity-0 pointer-events-none"
        )}
        onClick={() => setIsMobileSidebarOpen(false)}
        aria-hidden="true"
      />
    </div>
  );
}
