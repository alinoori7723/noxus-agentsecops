import { ShieldAlert, Workflow } from "lucide-react";

export function Hero() {
  return (
    <section className="nx-panel relative overflow-hidden px-7 py-8 sm:px-10 sm:py-10">
      <div
        className="pointer-events-none absolute inset-y-0 right-0 w-1/2 opacity-60"
        style={{
          backgroundImage:
            "repeating-linear-gradient(90deg, rgba(99,102,241,0.08) 0 1px, transparent 1px 88px)",
        }}
        aria-hidden
      />
      <div className="relative max-w-4xl">
        <span className="inline-flex items-center gap-2 rounded-full border border-accent/40 bg-accent/10 px-3 py-1 text-[11px] font-bold uppercase tracking-wide text-accent-soft">
          <Workflow size={13} /> Red Team / Blue Team readiness loop
        </span>
        <h1 className="mt-5 text-4xl font-black leading-[1.05] tracking-tight text-white sm:text-6xl">
          Noxus AgentSecOps
        </h1>
        <p className="mt-4 max-w-3xl text-lg leading-relaxed text-slate-300">
          Pre-production AI security readiness testing for enterprise LLM apps.
        </p>
        <p className="mt-3 flex items-start gap-2 text-sm leading-relaxed text-slate-400">
          <ShieldAlert size={16} className="mt-0.5 shrink-0 text-amber-400" />
          <span>
            Not a runtime firewall. Not a certification engine. A bounded
            readiness loop before production.
          </span>
        </p>
      </div>
    </section>
  );
}
