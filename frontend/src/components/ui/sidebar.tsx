"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  LayoutDashboard,
  FlaskConical,
  Bot,
  Database,
  ClipboardList,
  FileText,
  BarChart3,
  Settings,
  Shield,
  ChevronLeft,
  ChevronRight,
  Plus,
  ShieldCheck,
  Code2,
  Network,
  Activity,
  Bug,
} from "lucide-react";

const navigation = [
  { name: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { name: "Test Suites", href: "/suites", icon: FlaskConical },
  { name: "Target Agents", href: "/agents", icon: Bot },
  { name: "Evaluations", href: "/runs", icon: ClipboardList },
  { name: "Red Teaming", href: "/redteam", icon: Bug },
  { name: "Guardrails", href: "/guardrails", icon: ShieldCheck },
  { name: "Model Security", href: "/security", icon: Shield },
  { name: "Code Scanning", href: "/code-scan", icon: Code2 },
  { name: "MCP Proxy", href: "/mcp", icon: Network },
  { name: "Monitoring", href: "/monitoring", icon: Activity },
  { name: "Baselines", href: "/baselines", icon: Database },
  { name: "Reviews", href: "/reviews", icon: Shield },
  { name: "Reports", href: "/reports", icon: FileText },
  { name: "Analytics", href: "/analytics", icon: BarChart3 },
  { name: "Settings", href: "/settings", icon: Settings },
];

interface SidebarProps {
  isCollapsed: boolean;
  onToggle: () => void;
  isMobileOpen?: boolean;
  onCloseMobile?: () => void;
  className?: string;
}

export const Sidebar: React.FC<SidebarProps> = ({
  isCollapsed,
  onToggle,
  isMobileOpen = false,
  onCloseMobile,
  className,
}) => {
  const pathname = usePathname();

  return (
    <aside
      className={cn(
        "fixed left-0 top-0 z-50 h-screen border-r bg-card transition-all duration-300 flex flex-col",
        // On mobile the sidebar is off-canvas until it is explicitly opened.
        "lg:translate-x-0",
        isCollapsed ? "lg:w-16" : "lg:w-64",
        "w-64",
        isMobileOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0",
        className
      )}
      aria-label="Sidebar"
    >
      <div className="flex h-16 items-center justify-between border-b px-4">
        {!isCollapsed && (
          <Link href="/dashboard" className="flex items-center gap-2" onClick={onCloseMobile}>
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <Shield className="h-5 w-5" />
            </div>
            <span className="font-bold text-lg">RedTeam</span>
          </Link>
        )}
        <Button
          variant="ghost"
          size="icon"
          onClick={onToggle}
          className={cn("h-8 w-8", isCollapsed && "ml-auto")}
          aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {isCollapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
        </Button>
      </div>

      <nav className="flex-1 overflow-y-auto p-4 space-y-1" aria-label="Main navigation">
        {navigation.map((item) => {
          const isActive = pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <Link
              key={item.name}
              href={item.href}
              onClick={onCloseMobile}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                isActive
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                isCollapsed && "lg:justify-center"
              )}
              title={isCollapsed ? item.name : undefined}
            >
              <item.icon className="h-5 w-5 flex-shrink-0" aria-hidden="true" />
              {!isCollapsed && <span>{item.name}</span>}
            </Link>
          );
        })}
      </nav>

      <div className="border-t p-4">
        {!isCollapsed ? (
          <div className="space-y-2">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Quick Actions
            </p>
            <Button variant="outline" className="w-full justify-start gap-2" asChild>
              <Link href="/runs/new" onClick={onCloseMobile}>
                <Plus className="h-4 w-4" />
                <span>New Evaluation</span>
              </Link>
            </Button>
            <Button variant="outline" className="w-full justify-start gap-2" asChild>
              <Link href="/suites/new" onClick={onCloseMobile}>
                <Plus className="h-4 w-4" />
                <span>Create Suite</span>
              </Link>
            </Button>
          </div>
        ) : (
          <Button variant="outline" size="icon" className="w-full" asChild title="Quick Actions">
            <Link href="/runs/new" onClick={onCloseMobile}>
              <Plus className="h-4 w-4" />
            </Link>
          </Button>
        )}
      </div>
    </aside>
  );
};
