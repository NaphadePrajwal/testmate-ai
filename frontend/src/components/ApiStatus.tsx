import type { HealthResponse } from "../types/api";

interface ApiStatusProps {
  health: HealthResponse | null;
  error: string | null;
  loading: boolean;
}

export function ApiStatus({ health, error, loading }: ApiStatusProps) {
  const online = health?.status === "ok";
  const databaseConnected = health?.database.status === "connected";
  const label = loading ? "Checking API" : online ? "API online" : "API unavailable";

  return (
    <div className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white px-3 py-2 shadow-sm">
      <span className={`h-2.5 w-2.5 rounded-full ${loading ? "bg-amber-400" : online ? "bg-emerald-500" : "bg-rose-500"}`} />
      <div>
        <p className="text-xs font-semibold text-slate-700">{label}</p>
        <p className="text-[11px] text-slate-400">
          {error ?? (health ? `PostgreSQL ${databaseConnected ? "connected" : "not connected"}` : "Awaiting response")}
        </p>
      </div>
    </div>
  );
}
