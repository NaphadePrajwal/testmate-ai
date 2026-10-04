export function Brand() {
  return (
    <div className="flex items-center gap-3">
      <div className="grid h-10 w-10 place-items-center rounded-xl bg-violet-700 text-lg font-black text-white shadow-lg shadow-violet-700/20">T</div>
      <div>
        <p className="text-base font-bold tracking-tight text-slate-900">TestMate <span className="text-violet-700">AI</span></p>
        <p className="text-[10px] font-semibold uppercase tracking-[0.17em] text-slate-400">Testing intelligence</p>
      </div>
    </div>
  );
}
