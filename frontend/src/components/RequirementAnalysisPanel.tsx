import type { AnalysisItem, RequirementAnalysisResponse } from "../types/api";

interface RequirementAnalysisPanelProps { result: RequirementAnalysisResponse; }

const sourceStyles = {
  explicit: "bg-emerald-100 text-emerald-800",
  inferred: "bg-sky-100 text-sky-800",
  suggested: "bg-violet-100 text-violet-800",
  unspecified: "bg-slate-200 text-slate-700"
} as const;

function ItemList({ items }: { items: AnalysisItem[] }) {
  if (!items.length) return <p className="text-sm text-slate-500">None identified.</p>;
  return <ul className="space-y-2">{items.map((item, index) => <li key={`${item.text}-${index}`} className="flex gap-2 text-sm leading-6 text-slate-600"><span className={`mt-1 h-fit shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold ${sourceStyles[item.source]}`}>{item.source}</span><span>{item.text}</span></li>)}</ul>;
}

function Section({ title, items }: { title: string; items: AnalysisItem[] }) {
  return <section><h5 className="text-sm font-bold text-slate-800">{title}</h5><div className="mt-2"><ItemList items={items} /></div></section>;
}

export function RequirementAnalysisPanel({ result }: RequirementAnalysisPanelProps) {
  const { analysis, metadata } = result;
  return <section className="mt-5 rounded-xl border border-violet-200 bg-violet-50/50 p-5"><div className="flex flex-wrap items-center justify-between gap-2"><div><h4 className="font-bold text-slate-900">Requirement analysis</h4><p className="mt-1 text-xs text-slate-500">Explicit = source text; inferred = cautious interpretation; suggested = AI proposal; unspecified = not stated.</p></div><span className="rounded-full bg-white px-2.5 py-1 text-xs font-semibold text-violet-800">{analysis.requirement_type.classification.replace("_", " ")}</span></div>
    <div className="mt-5 grid gap-5 lg:grid-cols-2"><Section title="Summary" items={[analysis.summary]} /><Section title="Expected behavior" items={analysis.expected_behaviors} /><Section title="Actors and entities" items={analysis.actors_and_entities} /><Section title="Inputs" items={analysis.inputs} /><Section title="Outputs" items={analysis.outputs} /><Section title="Preconditions" items={analysis.preconditions} /><Section title="Postconditions" items={analysis.postconditions} /><Section title="Acceptance criteria" items={analysis.acceptance_criteria} /><Section title="Ambiguities and missing information" items={analysis.ambiguities_and_missing_information} /><Section title="Dependencies and constraints" items={analysis.dependencies_and_constraints} /><Section title="Clarification questions" items={analysis.clarification_questions} /></div>
    <section className="mt-5 border-t border-violet-200 pt-4"><h5 className="text-sm font-bold text-slate-800">Quality assessment</h5><p className="mt-1 text-sm text-slate-600">Clarity: <strong>{analysis.quality_assessment.clarity}</strong> · Completeness: <strong>{analysis.quality_assessment.completeness}</strong></p><div className="mt-2"><ItemList items={analysis.quality_assessment.reasons} /></div><p className="mt-3 text-xs leading-5 text-slate-500">{analysis.quality_assessment.limitation}</p></section>
    <p className="mt-4 text-xs text-slate-400">Analyzed with {metadata.provider}/{metadata.model} · prompt {metadata.prompt_version}</p>
  </section>;
}
