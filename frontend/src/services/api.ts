import type {
  DiagnosticAnalysis,
  DiagnosticDetail,
  Hypothesis,
  Session,
  Step,
  Vehicle,
  VehicleResolveResult,
  VinResolution,
} from "@/types";

export const API = typeof window === "undefined"
  ? (process.env.API_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api")
  : "/backend-api";

function detailMessage(value: unknown, fallback: string) {
  if (typeof value === "string") return value;
  if (value && typeof value === "object" && "code" in value) return String((value as { code: unknown }).code);
  return fallback;
}

async function call<T>(path: string, options?: RequestInit): Promise<T> {
  const multipart = options?.body instanceof FormData;
  const response = await fetch(`${API}${path}`, {
    ...options,
    credentials: "include",
    headers: {
      ...(multipart ? {} : { "Content-Type": "application/json" }),
      ...(options?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!response.ok) {
    let message = `Erreur ${response.status}`;
    try {
      const body = await response.json();
      message = detailMessage(body.detail, message);
    } catch {}
    if (response.status === 401 && typeof window !== "undefined" && window.location.pathname !== "/login") {
      window.location.assign("/login");
    }
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

type Page<T> = { items: T[]; page: number; page_size: number; total: number };

export const api = {
  login: (email: string, password: string) => call<{ user: { display_name: string; role: string } }>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  logout: () => call<void>("/auth/logout", { method: "POST" }),
  me: () => call<{ id: string; email: string; role: string; garage_id: string }>("/auth/me"),
  vehicles: () => call<Page<Vehicle>>("/vehicles").then((page) => page.items),
  sessions: () => call<Page<Session>>("/diagnostic-sessions").then((page) => page.items),
  session: (id: string) => call<Session>(`/diagnostic-sessions/${id}`),
  hypotheses: (id: string) => call<Page<Hypothesis>>(`/diagnostic-sessions/${id}/hypotheses`).then((page) => page.items),
  steps: (id: string) => call<Page<Step>>(`/diagnostic-sessions/${id}/steps`).then((page) => page.items),
  createSession: (body: unknown) => call<Session>("/diagnostic-sessions", { method: "POST", body: JSON.stringify(body) }),
  addObservation: (id: string, body: unknown) => call(`/diagnostic-sessions/${id}/observations`, { method: "POST", body: JSON.stringify(body) }),
  analyze: (id: string) => call(`/diagnostic-sessions/${id}/analyze`, { method: "POST" }),
  completeStep: (sessionId: string, stepId: string, body: unknown) => call<Step>(`/diagnostic-sessions/${sessionId}/steps/${stepId}/complete`, { method: "POST", body: JSON.stringify(body) }),
  completeSession: (id: string) => call(`/diagnostic-sessions/${id}/complete`, { method: "POST" }),
  report: (id: string) => call<Record<string, unknown>>(`/diagnostic-sessions/${id}/report`),
  validateVin: (vin: string) => call<{ is_valid_format: boolean; normalized_vin: string; warnings: string[]; errors: string[] }>("/vehicle-resolution/validate-vin", { method: "POST", body: JSON.stringify({ vin }) }),
  resolveVin: (body: unknown) => call<VinResolution>("/vehicle-resolution/vin", { method: "POST", body: JSON.stringify(body) }),
  resolveVehicle: (body: unknown) => call<VehicleResolveResult>("/vehicles/resolve", { method: "POST", body: JSON.stringify(body) }),
  resolveRegistrationNormalized: (body: unknown) => call("/vehicles/resolve-registration", { method: "POST", body: JSON.stringify(body) }),
  resolveVinNormalized: (body: unknown) => call("/vehicles/resolve-vin", { method: "POST", body: JSON.stringify(body) }),
  confirmResolution: (id: string, body: unknown) => call<{ vehicle: Vehicle; resolution: VinResolution }>(`/vehicle-resolution/${id}/confirm`, { method: "POST", body: JSON.stringify(body) }),
  createDiagnostic: (body: unknown) => call<Session>("/diagnostics", { method: "POST", body: JSON.stringify(body) }),
  addFaultCodes: (id: string, body: unknown) => call(`/diagnostics/${id}/fault-codes`, { method: "POST", body: JSON.stringify(body) }),
  addMeasurement: (id: string, body: unknown) => call(`/diagnostics/${id}/measurements`, { method: "POST", body: JSON.stringify(body) }),
  uploadImages: (id: string, data: FormData) => call(`/diagnostics/${id}/images`, { method: "POST", body: data }),
  analyzeDiagnostic: (id: string) => call<DiagnosticAnalysis>(`/diagnostics/${id}/analyze`, { method: "POST" }),
  diagnostic: (id: string) => call<DiagnosticDetail>(`/diagnostics/${id}`),
  submitStepResult: (caseId: string, stepId: string, body: unknown) => call<Step>(`/diagnostics/${caseId}/steps/${stepId}/result`, { method: "POST", body: JSON.stringify(body) }),
  reanalyzeDiagnostic: (id: string) => call<DiagnosticAnalysis>(`/diagnostics/${id}/reanalyze`, { method: "POST" }),
};
