"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const MODULES = [
  { href: "/diagnostics/new", glyph: "⊕", label: "Nouveau diagnostic" },
  { href: "/vehicle-resolution", glyph: "⌗", label: "Identification véhicule" },
];
const SOON = [
  { glyph: "≡", label: "Historique" },
  { glyph: "▤", label: "Base DTC" },
  { glyph: "▦", label: "Rapports" },
];

export function SideNav() {
  const path = usePathname();
  return (
    <nav aria-label="Modules" className="hidden w-56 shrink-0 border-r border-line bg-surface md:block">
      <div className="px-3 py-4">
        <p className="mb-2 px-2 text-[10px] font-bold uppercase tracking-wider text-muted">Modules</p>
        <ul className="space-y-0.5">
          {MODULES.map((m) => {
            const active = path === m.href || path.startsWith(m.href + "/");
            return (
              <li key={m.href}>
                <Link
                  href={m.href}
                  aria-current={active ? "page" : undefined}
                  className={`flex min-h-10 items-center gap-2.5 rounded-[2px] border-l-2 px-2.5 py-2 text-[13px] font-medium ${
                    active
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-transparent text-ink hover:bg-panel"
                  }`}
                >
                  <span aria-hidden="true" className="grid h-5 w-5 place-items-center font-mono text-[13px] text-muted">{m.glyph}</span>
                  {m.label}
                </Link>
              </li>
            );
          })}
        </ul>

        <p className="mb-2 mt-5 px-2 text-[10px] font-bold uppercase tracking-wider text-muted">Bientôt</p>
        <ul className="space-y-0.5">
          {SOON.map((m) => (
            <li key={m.label}>
              <span className="flex min-h-10 cursor-not-allowed items-center gap-2.5 rounded-[2px] px-2.5 py-2 text-[13px] text-slate-400">
                <span aria-hidden="true" className="grid h-5 w-5 place-items-center font-mono text-[13px]">{m.glyph}</span>
                {m.label}
                <span className="ml-auto rounded-[2px] border border-line px-1 text-[9px] uppercase tracking-wide text-slate-400">à venir</span>
              </span>
            </li>
          ))}
        </ul>
      </div>
    </nav>
  );
}
