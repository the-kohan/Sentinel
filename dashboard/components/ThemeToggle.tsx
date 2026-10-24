'use client';

import { useEffect, useState } from 'react';
import { motion } from 'motion/react';
import { Sun, Moon } from 'lucide-react';

// Exact palette from Draggable Cards reference, mapped to OUR CSS variable names
// Template uses: --background, --foreground, --card, --card-foreground, --muted-foreground, --border, --ring
// Our CSS uses: --bg, --fg, --surface, --muted, --border, --accent (via @theme mapping)
const THEMES = {
  light: {
    '--bg': '#ffffff',
    '--fg': '#09090b',
    '--surface': '#ffffff',
    '--muted': '#71717a',
    '--border': '#e4e4e7',
    '--accent': '#18181b',
    '--green': '#059669',
    '--yellow': '#d97706',
    '--red': '#dc2626',
  },
  dark: {
    '--bg': '#0a0a0b',
    '--fg': '#fafafa',
    '--surface': '#141417',
    '--muted': '#a1a1aa',
    '--border': '#27272a',
    '--accent': '#d4d4d8',
    '--green': '#34d399',
    '--yellow': '#fbbf24',
    '--red': '#f87171',
  },
};

export function ThemeToggle() {
  const [mode, setMode] = useState<'light' | 'dark'>(() => {
    if (typeof window === 'undefined') return 'dark';
    return window.matchMedia('(prefers-color-scheme: light)').matches
      ? 'light'
      : 'dark';
  });

  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    const root = document.documentElement;
    const theme = THEMES[mode];
    Object.entries(theme).forEach(([key, value]) => {
      root.style.setProperty(key, value);
    });
    // Also toggle html.light class for any CSS that uses it
    if (mode === 'light') {
      root.classList.add('light');
    } else {
      root.classList.remove('light');
    }
  }, [mode]);

  if (!mounted) {
    return (
      <button
        className="fixed top-4 right-4 z-50 size-10 rounded-full border border-[var(--border)] bg-[var(--surface)] text-[var(--fg)] transition-all duration-300"
        aria-hidden="true"
      >
        <Sun className="size-5" />
      </button>
    );
  }

  return (
    <button
      onClick={() => setMode((m) => (m === 'dark' ? 'light' : 'dark'))}
      className="fixed top-4 right-4 z-50 size-10 rounded-full border border-[var(--border)] bg-[var(--surface)] text-[var(--fg)] transition-all duration-300 hover:scale-105 hover:bg-[var(--surface-2)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
      aria-label={mode === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
      aria-pressed={mode === 'light'}
    >
      <motion.div
        initial={false}
        animate={{ rotate: mode === 'light' ? 180 : 0, scale: [1, 0.8, 1] }}
        transition={{ duration: 0.3, ease: 'easeInOut' }}
        className="flex size-full items-center justify-center"
      >
        {mode === 'dark' ? <Sun className="size-5" /> : <Moon className="size-5" />}
      </motion.div>
    </button>
  );
}
