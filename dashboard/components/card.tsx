import { cn } from "@/lib/utils";

export function Card({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4",
        className
      )}
    >
      {children}
    </div>
  );
}

export function CardTitle({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <h3 className={cn("text-sm font-medium text-[var(--muted)] mb-3", className)}>
      {children}
    </h3>
  );
}

export function Stat({
  label,
  value,
  accent = "text-[var(--fg)]",
}: {
  label: string;
  value: string | number;
  accent?: string;
}) {
  return (
    <div>
      <p className="text-xs text-[var(--muted)]">{label}</p>
      <p className={cn("text-2xl font-bold", accent)}>{value}</p>
    </div>
  );
}
