"use client";

import Link from "next/link";

export const FLOW_STEPS = ["Identification", "Vérification", "DTC & symptômes", "Résultats"] as const;

export function OrvectLogo({compact=false}:{compact?:boolean}){
 return <Link href="/diagnostics/new" className="inline-flex min-h-11 items-center gap-2" aria-label="ORVECT — accueil produit">
  <svg aria-hidden="true" className="h-[30px] w-9 shrink-0" viewBox="0 0 120 100" fill="currentColor"><path d="M8 76 29 24h19L27 76Z M41 76 70 4h19L60 76Z M74 76 95 24h19L93 76Z"/></svg>
  {!compact&&<strong className="text-[22px] font-bold tracking-[-.03em] text-orvect-mineral">ORVECT</strong>}
 </Link>
}

export function ProductTopBar(){
 return <header className="border-b border-white/10 bg-orvect-graphite text-orvect-mineral">
  <div className="flex min-h-[68px] w-full items-center gap-6 px-5 sm:px-8 xl:px-10 2xl:px-12">
   <div className="w-[190px] shrink-0 text-orvect-orange"><OrvectLogo/></div>
   <p className="hidden flex-1 text-xs font-medium tracking-[.08em] sm:block">ATELIER ORVECT / PROTOTYPE TECHNIQUE</p>
   <span className="ml-auto text-right text-xs font-medium uppercase tracking-[.08em] text-orvect-alloy">Mode démonstration VAG</span>
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
 return <aside className="hidden w-[260px] shrink-0 self-stretch bg-orvect-graphite px-6 py-8 text-orvect-mineral lg:flex lg:min-h-[calc(100dvh-68px)] lg:flex-col">
  <p className="orvect-label text-orvect-alloy">DIAGNOSTIC ASSISTÉ</p>
  <ol className="mt-5 space-y-1">
   {FLOW_STEPS.map((label,index)=><li key={label} className={`px-3 py-3 text-sm ${index+1===active?"bg-orvect-orange text-orvect-graphite":"text-orvect-mineral"}`}>
    {String(index+1).padStart(2,"0")} / {label}
   </li>)}
  </ol>
  <p className="mt-auto border-t border-white/15 pt-5 text-xs leading-5 text-orvect-alloy">VIN ou plaque pour identifier. Confirmation technicien avant toute analyse.</p>
 </aside>
}

export function ProductLayout({active,children}:{active:number;children:React.ReactNode}){
 return <div className="min-h-dvh bg-orvect-mineral text-orvect-graphite">
  <ProductTopBar/>
  <div className="flex min-h-[calc(100dvh-68px)] w-full items-stretch">
   <ProductSidebar active={active}/>
   <main className="min-w-0 flex-1 px-5 py-6 sm:px-8 sm:py-8 xl:px-10 2xl:px-12">{children}</main>
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

// --- Evidence, confidence and research transparency ---------------------

const SOURCE_TYPE_LABELS:Record<string,string>={
 oem_manufacturer:"Constructeur / OEM",
 safety_authority:"Autorité de sécurité",
 technical_documentation:"Documentation technique",
 repair_technical_resource:"Ressource technique réparation",
 specialist_community:"Communauté spécialisée",
 general_web:"Web généraliste",
};
const SOURCE_TYPE_RANK:Record<string,number>={oem_manufacturer:6,safety_authority:5,technical_documentation:4,repair_technical_resource:3,specialist_community:2,general_web:1};

export function sourceTypeLabel(type:string){return SOURCE_TYPE_LABELS[type]??type.replaceAll("_"," ")}
export function sourceTypeRank(type:string){return SOURCE_TYPE_RANK[type]??0}

/** One retrieved technical source. Only ever links to a URL Tavily returned. */
export function EvidenceCard({source}:{source:import("@/types").SourceReference}){
 const rank=sourceTypeRank(source.source_type);
 const tone=rank>=5?"border-orvect-graphite":rank>=3?"border-orvect-alloy":"border-dashed border-orvect-alloy";
 return <article className={`border ${tone} bg-white p-4`}>
  <div className="flex flex-wrap items-center justify-between gap-2">
   <span className="orvect-label text-slate-500">{sourceTypeLabel(source.source_type)}</span>
   {source.domain&&<span className="font-mono text-[11px] text-slate-500">{source.domain}</span>}
  </div>
  <h4 className="mt-2 text-sm font-medium leading-5">{source.title||source.source_id}</h4>
  <div className="mt-3 flex flex-wrap items-center gap-3 text-[11px] uppercase tracking-[.04em] text-slate-500">
   <span className="border border-orvect-alloy px-2 py-1">{source.verified?"SOURCE VÉRIFIÉE":"NON VÉRIFIÉE"}</span>
   {source.url
    ?<a href={source.url} target="_blank" rel="noopener noreferrer nofollow" className="font-medium text-orvect-graphite underline underline-offset-2 hover:text-orvect-orange">Ouvrir la source ↗</a>
    :<span>Lien indisponible</span>}
  </div>
 </article>
}

/** Heuristic diagnostic confidence — explicitly not a repair-success probability. */
export function ConfidencePanel({confidence}:{confidence:import("@/types").DiagnosticConfidence}){
 const labels:Record<string,string>={low:"Faible",moderate:"Modérée",good:"Bonne",strong:"Élevée"};
 return <section className="orvect-panel">
  <div className="flex flex-wrap items-end justify-between gap-4">
   <div>
    <p className="orvect-label text-slate-500">CONFIANCE DIAGNOSTIQUE</p>
    <p className="mt-2 text-5xl font-bold tracking-[-.04em]">{confidence.score}<span className="text-2xl"> %</span></p>
    <p className="mt-1 text-sm text-slate-600">Qualité de l’étayage : {labels[confidence.label]??confidence.label}</p>
   </div>
   <p className="max-w-sm text-xs leading-5 text-slate-500">Mesure la solidité des preuves réunies, <strong>pas</strong> la probabilité qu’une réparation fonctionne. Le diagnostic final reste celui du technicien.</p>
  </div>
  <div className="mt-4 h-2 w-full bg-orvect-alloy/40" role="img" aria-label={`Confiance diagnostique ${confidence.score} %`}>
   <div className="h-2 bg-orvect-orange" style={{width:`${confidence.score}%`}}/>
  </div>
  <div className="mt-5 grid gap-5 md:grid-cols-2">
   <div>
    <p className="orvect-label text-slate-500">CE QUI L’ÉTAYE</p>
    <ul className="mt-2 space-y-1 text-sm">{confidence.factors.map(item=><li key={item} className="border-t border-orvect-alloy pt-1">{item}</li>)}</ul>
   </div>
   {confidence.improvedBy.length>0&&<div>
    <p className="orvect-label text-slate-500">CE QUI L’AMÉLIORERAIT</p>
    <ul className="mt-2 space-y-1 text-sm">{confidence.improvedBy.map(item=><li key={item} className="border-t border-orvect-alloy pt-1">{item}</li>)}</ul>
   </div>}
  </div>
 </section>
}

/** Concise process metadata. Never chain-of-thought. */
export function ResearchTransparency({research,hypothesisCount,codeCount}:{research:import("@/types").ResearchMetadata;hypothesisCount:number;codeCount:number}){
 const mix=Object.entries(research.sourceMix||{}).sort((a,b)=>sourceTypeRank(b[0])-sourceTypeRank(a[0]));
 const summary=research.researchTriggered
  ? `Orvect a analysé ${codeCount} code${codeCount>1?"s":""} défaut, retenu ${hypothesisCount} hypothèse${hypothesisCount>1?"s":""}, lancé ${research.searchCount} recherche${research.searchCount>1?"s":""} technique${research.searchCount>1?"s":""} externe${research.searchCount>1?"s":""} et consulté ${research.externalSources} source${research.externalSources>1?"s":""}${research.fromCache?" (réutilisées depuis le cache)":""}.`
  : `Orvect a analysé ${codeCount} code${codeCount>1?"s":""} défaut et retenu ${hypothesisCount} hypothèse${hypothesisCount>1?"s":""} à partir de sa base interne, sans recherche externe.`;
 return <details className="border border-orvect-alloy bg-white">
  <summary className="cursor-pointer p-5 font-medium">Comment Orvect est arrivé à cette conclusion</summary>
  <div className="space-y-5 border-t border-orvect-alloy p-5">
   <p className="text-sm leading-6">{summary}</p>
   <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
    <Metric label="RECHERCHE EXTERNE" value={research.researchTriggered?"Déclenchée":"Non nécessaire"}/>
    <Metric label="SOURCES INTERNES" value={String(research.internalSources)}/>
    <Metric label="SOURCES EXTERNES" value={String(research.externalSources)}/>
    <Metric label="MOTEUR" value={research.provider==="nebius"?"Nebius Token Factory":research.provider??"—"}/>
   </div>
   {research.model&&<p className="font-mono text-[11px] text-slate-500">modèle : {research.model}{research.durationMs?` · ${(research.durationMs/1000).toFixed(1)} s`:""}{research.tokenUsage?.total_tokens?` · ${research.tokenUsage.total_tokens} tokens`:""}</p>}
   {research.researchReasons.length>0&&<div>
    <p className="orvect-label text-slate-500">POURQUOI CETTE DÉCISION DE RECHERCHE</p>
    <ul className="mt-2 flex flex-wrap gap-2">{research.researchReasons.map(item=><li key={item} className="border border-orvect-alloy px-2 py-1 font-mono text-[11px]">{item}</li>)}</ul>
   </div>}
   {research.queries.length>0&&<div>
    <p className="orvect-label text-slate-500">REQUÊTES TECHNIQUES ENVOYÉES</p>
    <ul className="mt-2 space-y-1 text-sm">{research.queries.map(item=><li key={item} className="border-t border-orvect-alloy pt-1 font-mono text-xs">{item}</li>)}</ul>
   </div>}
   {mix.length>0&&<div>
    <p className="orvect-label text-slate-500">QUALITÉ DES SOURCES TROUVÉES</p>
    <ul className="mt-2 flex flex-wrap gap-2 text-xs">{mix.map(([type,count])=><li key={type} className="border border-orvect-alloy px-2 py-1">{sourceTypeLabel(type)} · {count}</li>)}</ul>
   </div>}
   {research.researchError&&<p className="border border-orvect-orange bg-orange-50 p-3 text-sm">Vérification externe indisponible : {research.researchError}. Le dossier s’appuie uniquement sur la base interne.</p>}
  </div>
 </details>
}

function Metric({label,value}:{label:string;value:string}){
 return <div className="border border-orvect-alloy p-3">
  <p className="orvect-label text-slate-500">{label}</p>
  <p className="mt-1 text-sm font-medium">{value}</p>
 </div>
}

/** Live pipeline position, driven by real backend stages. */
export function AnalysisStages({progress}:{progress:import("@/types").AnalysisProgress|null}){
 const stages=progress?.stages??[];
 const current=progress?.index??0;
 return <section className="orvect-panel-dark" aria-live="polite">
  <p className="orvect-label text-orvect-alloy">DIAGNOSTIC EN COURS</p>
  <h2 className="mt-2 text-3xl font-medium">{progress?.label||"Démarrage de l’analyse"}</h2>
  {progress?.detail&&<p className="mt-1 text-sm text-orvect-alloy">{progress.detail}</p>}
  <ol className="mt-5 space-y-2">
   {stages.map((stage,index)=>{
    const state=index<current?"done":index===current?"active":"pending";
    return <li key={stage.key} className={`flex items-center gap-3 border p-3 text-sm ${state==="active"?"border-orvect-orange bg-orvect-orange text-orvect-graphite":state==="done"?"border-white/25 text-orvect-mineral":"border-white/10 text-orvect-alloy"}`}>
     <span className="font-mono text-xs">{state==="done"?"✓":String(index+1).padStart(2,"0")}</span>
     <span>{stage.label}</span>
    </li>})}
  </ol>
  {progress?.elapsedMs?<p className="mt-4 text-xs text-orvect-alloy">{(progress.elapsedMs/1000).toFixed(1)} s écoulées</p>:null}
 </section>
}
