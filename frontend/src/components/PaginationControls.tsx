interface PaginationControlsProps {
  total: number;
  limit: number;
  offset: number;
  onChange: (offset: number) => void;
}

export function PaginationControls({ total, limit, offset, onChange }: PaginationControlsProps) {
  if (total <= limit) return null;

  const first = offset + 1;
  const last = Math.min(offset + limit, total);

  return (
    <nav className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm" aria-label="Pagination">
      <p className="text-slate-500">Showing {first}–{last} of {total}</p>
      <div className="flex gap-2">
        <button type="button" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))} className="rounded-lg border border-slate-300 px-3 py-1.5 font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50">Previous</button>
        <button type="button" disabled={offset + limit >= total} onClick={() => onChange(offset + limit)} className="rounded-lg border border-slate-300 px-3 py-1.5 font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50">Next</button>
      </div>
    </nav>
  );
}
