"use client";

import {FormEvent,useState} from "react";
import {useRouter} from "next/navigation";
import {api} from "@/services/api";
import {OrvectLogo} from "@/components/OrvectProduct";

export default function LoginPage(){
 const router=useRouter();const [email,setEmail]=useState("");const [password,setPassword]=useState("");const [busy,setBusy]=useState(false);const [error,setError]=useState("");
 async function submit(event:FormEvent){event.preventDefault();setBusy(true);setError("");try{await api.login(email,password);router.replace("/diagnostics/new")}catch(value){setError(value instanceof Error?value.message:"Connexion impossible")}finally{setBusy(false)}}
 return <main className="grid min-h-dvh bg-orvect-graphite px-5 py-10 text-orvect-mineral lg:grid-cols-2 lg:items-stretch lg:p-0">
  <section className="flex flex-col justify-between p-3 lg:p-12"><div className="text-orvect-orange"><OrvectLogo/></div><div className="my-16 max-w-xl"><p className="orvect-label text-orvect-alloy">ACCÈS ATELIER</p><h1 className="mt-6 text-5xl font-bold leading-[1.02] tracking-[-.045em] sm:text-7xl">Beyond the<br/>fault code.</h1><p className="mt-6 max-w-lg text-lg text-orvect-alloy">Automotive intelligence. Grounded in evidence.</p></div><p className="text-xs text-orvect-alloy">EARLY TECHNICAL PROTOTYPE · LE TECHNICIEN GARDE LE CONTRÔLE</p></section>
  <section className="flex items-center justify-center bg-orvect-mineral p-5 text-orvect-graphite sm:p-10"><form onSubmit={submit} className="w-full max-w-md border border-orvect-alloy p-6 sm:p-8"><p className="orvect-label">SESSION SÉCURISÉE</p><h2 className="mt-5 text-4xl font-bold tracking-[-.04em]">Connexion à ORVECT</h2><p className="mt-3 text-sm text-slate-600">Le garage actif sera dérivé de cette session côté serveur.</p>{error&&<div role="alert" className="mt-5 border border-red-500 bg-red-50 p-3 text-red-800">{error}</div>}<label className="orvect-field-label mt-6" htmlFor="email">E-mail</label><input id="email" className="orvect-field" type="email" autoComplete="username" value={email} onChange={event=>setEmail(event.target.value)} required/><label className="orvect-field-label mt-4" htmlFor="password">Mot de passe</label><input id="password" className="orvect-field" type="password" autoComplete="current-password" value={password} onChange={event=>setPassword(event.target.value)} minLength={8} required/><button className="orvect-button-primary mt-6 w-full" disabled={busy}>{busy?"Connexion…":"Ouvrir l’atelier"}</button></form></section>
 </main>
}
