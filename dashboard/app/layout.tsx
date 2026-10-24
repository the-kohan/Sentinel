import "./globals.css";
import type { Metadata } from "next";
import { ThemeToggle } from "@/components/ThemeToggle";

export const metadata: Metadata = {
  title: "Sentinel Dashboard",
  description: "God-mode network guard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <ThemeToggle />
        <main className="flex min-h-screen w-full overflow-y-auto px-4 py-12 text-foreground antialiased">
          {children}
        </main>
      </body>
    </html>
  );
}
