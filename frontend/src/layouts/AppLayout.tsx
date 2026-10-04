import type { ReactNode } from "react";
import { Brand } from "../components/Brand";

interface AppLayoutProps {
  children: ReactNode;
  activePage: "Dashboard" | "Projects";
  onNavigate: (page: "Dashboard" | "Projects") => void;
  status: ReactNode;
}

const navItems = ["Dashboard", "Projects"] as const;

export function AppLayout({ children, activePage, onNavigate, status }: AppLayoutProps) {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <aside className="fixed inset-y-0 hidden w-64 border-r border-slate-200 bg-white p-5 lg:block">
        <Brand />
        <nav className="mt-12 space-y-1" aria-label="Main navigation">
          {navItems.map((item) => (
            <button key={item} onClick={() => onNavigate(item)} className={`flex w-full items-center rounded-xl px-4 py-3 text-left text-sm font-semibold transition ${activePage === item ? "bg-violet-50 text-violet-800" : "text-slate-500 hover:bg-slate-50 hover:text-slate-900"}`}>
              <span className="mr-3 text-base">{item === "Dashboard" ? "▦" : "□"}</span>{item}
            </button>
          ))}
        </nav>
        <div className="absolute bottom-6 left-5 right-5 rounded-xl bg-slate-900 p-4 text-xs leading-5 text-slate-300">
          <p className="font-semibold text-white">Phase 0 foundation</p>
          <p className="mt-1">AI analysis, test automation and reporting modules will build on this workspace.</p>
        </div>
      </aside>
      <main className="lg:ml-64">
        <header className="flex min-h-20 items-center justify-between border-b border-slate-200 bg-white px-5 sm:px-8">
          <div className="lg:hidden"><Brand /></div>
          <div className="hidden lg:block" />
          {status}
        </header>
        <section className="mx-auto max-w-6xl px-5 py-8 sm:px-8">{children}</section>
      </main>
    </div>
  );
}
