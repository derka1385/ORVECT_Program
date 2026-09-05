"use client";

import Link from "next/link";
import {useRouter} from "next/navigation";
import {api} from "@/services/api";

export const FLOW_STEPS = ["Identification", "Vérification", "DTC & symptômes", "Résultats"] as const;

export function OrvectLogo({compact=false}:{compact?:boolean}){
 return <Link href="/diagnostics/new" className="inline-flex min-h-11 items-center gap-2" aria-label="ORVECT — accueil produit">
  <svg aria-hidden="true" className="h-[30px] w-9 shrink-0" viewBox="0 0 120 100" fill="currentColor"><path d="M8 76 29 24h19L27 76Z M41 76 70 4h19L60 76Z M74 76 95 24h19L93 76Z"/></svg>
  {!compact&&<strong className="text-[22px] font-bold tracking-[-.03em] text-orvect-mineral">ORVECT</strong>}
 </Link>
}

export function ProductTopBar({identity="Session atelier"}:{identity?:string}){
 const router=useRouter();
 async function logout(){await api.logout().catch(()=>undefined);router.replace("/login")}
 return <header className="border-b border-white/10 bg-orvect-graphite text-orvect-mineral">
  <div className="flex min-h-[68px] w-full items-center gap-6 px-5 sm:px-8 xl:px-10 2xl:px-12">
   <div className="w-[190px] shrink-0 text-orvect-orange"><OrvectLogo/></div>
   <p className="hidden flex-1 text-xs font-medium tracking-[.08em] sm:block">ATELIER ORVECT / PROTOTYPE TECHNIQUE</p>
   <div className="ml-auto flex items-center gap-3 text-right text-xs text-orvect-alloy">
    <span className="hidden max-w-[260px] truncate md:block">{identity}</span>
    <button type="button" onClick={logout} className="orvect-link-button">Déconnexion</button>
   </div>
  </div>
 </header>
}

export function FlowProgress({active,onNavigate}:{active:number;onNavigate?:(step:number)=>void}){
 return <ol className="grid grid-cols-2 gap-2 sm:grid-cols-4" aria-label="Progression du diagnostic">
  {FLOW_STEPS.map((label,index)=>{const n=index+1;const enabled=Boolean(onNavigate)&&n<active;return <li key={label}>
   <button type="button" disabled={!enabled} onClick={()=>onNavigate?.(n)} aria-current={n===active?"step":undefined} className={`w-full border px-3 py-3 text-left text-xs transition-colors ${n===active?"border-orvect-orange bg-orvect-orange text-orvect-graphite":"border-orvect-alloy bg-transparent text-orvect-graphite enabled:hover:border-orvect-graphite"}`}>
    {String(n).padStart(2,"0")} / {label}
   </button>
  </li>})}
 </ol>
}

export function ProductSidebar({active}:{active:number}){
 return <aside className="hidden w-[216px] shrink-0 bg-orvect-graphite p-5 text-orvect-mineral lg:block">
  <p className="orvect-label text-orvect-alloy">DIAGNOSTIC ASSISTÉ</p>
  <ol className="mt-5 space-y-1">
   {FLOW_STEPS.map((label,index)=><li key={label} className={`px-3 py-3 text-sm ${index+1===active?"bg-orvect-orange text-orvect-graphite":"text-orvect-mineral"}`}>
    {String(index+1).padStart(2,"0")} / {label}
   </li>)}
  </ol>
  <p className="mt-8 border-t border-white/15 pt-5 text-xs leading-5 text-orvect-alloy">VIN ou plaque pour identifier. Confirmation technicien avant toute analyse.</p>
 </aside>
}

export function ProductLayout({active,identity,children}:{active:number;identity?:string;children:React.ReactNode}){
 return <div className="min-h-dvh bg-orvect-mineral text-orvect-graphite">
  <ProductTopBar identity={identity}/>
  <div className="flex w-full items-start gap-5 px-5 py-6 sm:px-8 sm:py-8 xl:gap-8 xl:px-10 2xl:px-12">
   <ProductSidebar active={active}/>
   <main className="min-w-0 flex-1">{children}</main>
  </div>
 </div>
}

export function SectionIntro({label,title,description}:{label:string;title:React.ReactNode;description:string}){
 return <div>
  <p className="orvect-label">{label}</p>
  <h1 className="mt-5 max-w-[920px] text-[clamp(2.45rem,5vw,4rem)] font-bold leading-[1.02] tracking-[-.045em]">{title}</h1>
  <p className="mt-5 max-w-[980px] text-base leading-6">{description}</p>
 </div>
}

export function StatusLabel({children,tone="neutral"}:{children:React.ReactNode;tone?:"neutral"|"signal"|"dark"}){
 return <div className={`border px-4 py-4 text-sm font-medium uppercase tracking-[.02em] ${tone==="signal"?"border-orvect-orange bg-orvect-orange text-orvect-graphite":tone==="dark"?"border-orvect-alloy bg-orvect-graphite text-orvect-mineral":"border-orvect-alloy bg-orvect-mineral text-orvect-graphite"}`}>{children}</div>
}

export function SourceLabel({title,children,dark=false}:{title:string;children:React.ReactNode;dark?:boolean}){
 return <div className={`border p-4 text-xs leading-5 ${dark?"border-white/25 bg-orvect-graphite text-orvect-mineral":"border-orvect-alloy bg-orvect-mineral text-orvect-graphite"}`}>
  <p className="font-medium uppercase">{title}</p>
  <div className={`mt-2 ${dark?"text-orvect-alloy":"text-orvect-graphite"}`}>{children}</div>
 </div>
}
