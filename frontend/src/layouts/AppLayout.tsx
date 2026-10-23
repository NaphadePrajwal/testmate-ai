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
    <div className="min-h-screen bg-slate-50 text-slate-900 print:bg-white">
      <aside className="fixed inset-y-0 hidden w-64 border-r border-slate-200 bg-white p-5 lg:block print:hidden">
        <Brand />
        <nav className="mt-12 space-y-1" aria-label="Main navigation">
          {navItems.map((item) => (
            <button key={item} onClick={() => onNavigate(item)} className={`flex w-full items-center rounded-xl px-4 py-3 text-left text-sm font-semibold transition ${activePage === item ? "bg-violet-50 text-violet-800" : "text-slate-500 hover:bg-slate-50 hover:text-slate-900"}`}>
              <span className="mr-3 text-base">{item === "Dashboard" ? "▦" : "□"}</span>{item}
            </button>
          ))}
        </nav>
        <div className="absolute bottom-6 left-5 right-5 rounded-xl bg-slate-900 p-4 text-xs leading-5 text-slate-300">
          <p className="font-semibold text-white">TestMate AI Platform</p>
          <p className="mt-1">Autonomous QA, Playwright test execution, LangGraph workflows, and failure intelligence.</p>
        </div>
      </aside>
      <main className="lg:ml-64 print:ml-0">
        <header className="flex min-h-20 items-center justify-between border-b border-slate-200 bg-white px-5 sm:px-8 print:hidden">
          <div className="lg:hidden"><Brand /></div>
          <nav className="flex items-center gap-1 lg:hidden" aria-label="Mobile navigation">
            {navItems.map((item) => (
              <button key={item} type="button" onClick={() => onNavigate(item)} className={`rounded-lg px-2.5 py-2 text-xs font-semibold ${activePage === item ? "bg-violet-50 text-violet-800" : "text-slate-500 hover:bg-slate-50"}`}>
                {item}
              </button>
            ))}
          </nav>
          <div className="hidden lg:block" />
          {status}
        </header>
        <section className="mx-auto max-w-6xl px-5 py-8 sm:px-8 print:max-w-none print:px-0 print:py-0">{children}</section>
      </main>
    </div>
  );
}
