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
    <>
      <nav aria-label="Modules" className="hidden w-56 shrink-0 self-start border-r border-white/10 bg-orvect-graphite text-orvect-mineral md:block md:sticky md:top-[93px] md:h-[calc(100dvh-93px)] md:overflow-y-auto">
        <div className="px-3 py-5">
          <p className="mb-2 px-2 text-[10px] font-bold uppercase tracking-wider text-orvect-alloy">Modules</p>
          <ul className="space-y-0.5">
            {MODULES.map((m) => {
              const active = path === m.href || path.startsWith(m.href + "/");
              return (
                <li key={m.href}>
                  <Link
                    href={m.href}
                    aria-current={active ? "page" : undefined}
                    className={`flex min-h-10 items-center gap-2.5 border-l-2 px-2.5 py-2 text-[13px] font-medium transition-colors ${
                      active
                        ? "border-orvect-orange bg-orvect-orange/10 text-orvect-orange"
                        : "border-transparent text-orvect-mineral hover:bg-white/5"
                    }`}
                  >
                    <span aria-hidden="true" className="grid h-5 w-5 place-items-center font-mono text-[13px] text-orvect-alloy">{m.glyph}</span>
                    {m.label}
                  </Link>
                </li>
              );
            })}
          </ul>

          <p className="mb-2 mt-5 px-2 text-[10px] font-bold uppercase tracking-wider text-orvect-alloy">Bientôt</p>
          <ul className="space-y-0.5">
            {SOON.map((m) => (
              <li key={m.label}>
                <span className="flex min-h-10 cursor-not-allowed items-center gap-2.5 px-2.5 py-2 text-[13px] text-orvect-alloy/60">
                  <span aria-hidden="true" className="grid h-5 w-5 place-items-center font-mono text-[13px]">{m.glyph}</span>
                  {m.label}
                  <span className="ml-auto border border-white/15 px-1 text-[9px] uppercase tracking-wide">à venir</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      </nav>

      <nav aria-label="Modules mobiles" className="border-b border-white/10 bg-orvect-graphite text-orvect-mineral md:hidden">
        <ul className="flex max-w-full overflow-x-auto px-3" role="list">
          {MODULES.map((m) => {
            const active = path === m.href || path.startsWith(m.href + "/");
            return (
              <li key={m.href} className="shrink-0">
                <Link
                  href={m.href}
                  aria-current={active ? "page" : undefined}
                  className={`flex min-h-12 items-center gap-2 border-b-2 px-3 text-[12px] font-medium transition-colors ${
                    active
                      ? "border-orvect-orange text-orvect-orange"
                      : "border-transparent text-orvect-mineral"
                  }`}
                >
                  <span aria-hidden="true" className="font-mono text-orvect-alloy">{m.glyph}</span>
                  {m.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </>
  );
}
