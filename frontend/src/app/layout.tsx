import type {Metadata} from "next";import "./globals.css";import {Shell} from "@/components/Shell";
export const metadata:Metadata={title:"ORVECT — Diagnostic assisté",description:"Automotive intelligence. Grounded in evidence."};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="fr"><body><Shell>{children}</Shell></body></html>}
