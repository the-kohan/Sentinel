import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(iso: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("en-GB", { timeZone: "Africa/Nairobi" });
}

export function timeAgo(iso: string): string {
  if (!iso) return "—";
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function verdictColor(v: string): string {
  switch (v) {
    case "benign": return "text-green-400";
    case "suspicious": return "text-red-400";
    default: return "text-yellow-400";
  }
}

export function verdictBg(v: string): string {
  switch (v) {
    case "benign": return "bg-green-400/10";
    case "suspicious": return "bg-red-400/10";
    default: return "bg-yellow-400/10";
  }
}

export function severityColor(s: number): string {
  if (s >= 5) return "text-red-400";
  if (s >= 4) return "text-orange-400";
  if (s >= 3) return "text-yellow-400";
  return "text-muted";
}

export function sourceIcon(source: string): string {
  switch (source) {
    case "docker": return "🐳";
    case "host": return "💻";
    case "pcap": return "📡";
    default: return "❓";
  }
}
