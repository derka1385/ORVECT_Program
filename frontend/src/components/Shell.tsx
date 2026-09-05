"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { SideNav } from "@/components/SideNav";
import { api } from "@/services/api";

const FULLSCREEN_ROUTES = ["/diagnostics/new", "/login"];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  async function logout() {
    await api.logout().catch(() => undefined);
    router.replace("/login");
  }
  if (FULLSCREEN_ROUTES.includes(pathname) || pathname.startsWith("/diagnostics/ai/")) return <>{children}</>;

  return (
    <div className="flex min-h-dvh flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-[2px] focus:bg-primary focus:p-3 focus:text-white">
        Aller au contenu
      </a>

      {/* Barre de titre applicative */}
      <header className="sticky top-0 z-30 border-b border-line bg-surface">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-2.5 md:px-8">
          <Link href="/diagnostics/new" className="flex min-h-11 items-center gap-2.5 rounded-[2px]">
            <span aria-hidden="true" className="grid h-9 w-9 place-items-center rounded-[2px] bg-primary text-[17px] font-black text-white">
              ◈
            </span>
            <span className="leading-tight">
              <strong className="block text-[15px] font-bold tracking-tight text-ink">DiagPilot</strong>
              <span className="text-[11px] text-muted">Assistant diagnostic — atelier</span>
            </span>
          </Link>

          <div className="flex items-center gap-3">
            <span className="hidden items-center gap-2 rounded-[2px] border border-line bg-panel px-2.5 py-1.5 font-mono text-[11px] text-slate-600 sm:inline-flex">
              <span className="led" aria-hidden="true" />
              Système prêt
            </span>
            <Link className="btn-primary" href="/diagnostics/new">Nouveau diagnostic</Link>
            <button className="btn-secondary" type="button" onClick={logout}>Déconnexion</button>
          </div>
        </div>

        {/* Bandeau mode démonstration */}
        <div className="border-t border-amber-200 bg-amber-50">
          <div className="mx-auto flex max-w-7xl items-center gap-2 px-4 py-1.5 font-mono text-[11px] text-amber-800 md:px-8">
            <span className="led led-amber" aria-hidden="true" />
            Mode démonstration — données non contractuelles, aucune commande de calculateur
          </div>
        </div>
      </header>

      <div className="mx-auto flex w-full max-w-7xl flex-1">
        <SideNav />
        <main id="main" className="min-w-0 flex-1 px-4 py-7 md:px-8">
          {children}
        </main>
      </div>

      {/* Barre de statut */}
      <footer className="border-t border-line bg-panel">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-2 px-4 py-2 font-mono text-[11px] text-muted md:px-8">
          <span className="flex items-center gap-2">
            <span className="led led-muted" aria-hidden="true" />
            Aide à la décision · aucun remplacement de pièce sans contrôle de confirmation
          </span>
          <span>DiagPilot v0.1 · le jugement professionnel reste indispensable</span>
        </div>
      </footer>
    </div>
  );
}
