"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  Network,
  Activity,
  AlertTriangle,
  Shield,
  BookOpen,
  Volume2,
  Search,
} from "lucide-react";

const navItems = [
  { href: "/topology", label: "Topology", icon: Network },
  { href: "/events", label: "Events", icon: Activity },
  { href: "/anomalies", label: "Anomalies", icon: AlertTriangle },
  { href: "/incidents", label: "Incidents", icon: Shield },
  { href: "/reputation", label: "Reputation", icon: BookOpen },
  { href: "/allowlist", label: "Allowlist", icon: Volume2 },
  { href: "/queries", label: "Queries", icon: Search },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-56 flex-shrink-0 border-r border-[var(--border)] bg-[var(--surface)] flex flex-col">
      <div className="p-4 border-b border-[var(--border)]">
        <h1 className="text-lg font-bold text-[var(--fg)] flex items-center gap-2">
          <Shield className="w-5 h-5 text-[var(--accent)]" />
          Sentinel
        </h1>
        <p className="text-xs text-[var(--muted)] mt-1">God-mode network guard</p>
      </div>
      <nav className="flex-1 p-2 space-y-1">
        {navItems.map((item) => {
          const active = pathname === item.href;
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors",
                active
                  ? "bg-[var(--accent)]/10 text-[var(--accent)]"
                  : "text-[var(--muted)] hover:bg-[var(--surface-2)] hover:text-[var(--fg)]"
              )}
            >
              <Icon className="w-4 h-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="p-4 border-t border-[var(--border)] text-xs text-[var(--muted)]">
        v1.0-alpha • Local-first
      </div>
    </aside>
  );
}
