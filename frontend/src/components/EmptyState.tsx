interface EmptyStateProps {
  title: string;
  detail: string;
}

export function EmptyState({ title, detail }: EmptyStateProps) {
  return (
    <div className="rounded-2xl border border-dashed border-violet-200 bg-violet-50/60 px-6 py-12 text-center">
      <div className="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-2xl bg-violet-100 text-xl text-violet-700">+</div>
      <h3 className="font-semibold text-slate-800">{title}</h3>
      <p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-slate-500">{detail}</p>
    </div>
  );
}
