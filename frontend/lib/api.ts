// Deployed API. Used unless NEXT_PUBLIC_API_URL overrides it at build time.
// A value of "/bff" keeps same-origin proxying for local development.
const DEFAULT_API_ORIGIN = "https://fintech-intelligence-pmuw.onrender.com";
const RAW = (process.env.NEXT_PUBLIC_API_URL ?? DEFAULT_API_ORIGIN).trim();
const API_ORIGIN = RAW.replace(/\/+$/, "");
export const API = API_ORIGIN && API_ORIGIN !== "/bff"
  ? `${API_ORIGIN}/api/v1`
  : "/bff/api/v1";

export type Env<T = any> = {
  value: T | null;
  status: string;
  note: string;
};

const CLIENT_KEY = "bfi_client_id";

function clientId(): string {
  if (typeof window === "undefined") return "default";
  let id = window.localStorage.getItem(CLIENT_KEY);
  if (!id) {
    const uuid =
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    id = uuid;
    window.localStorage.setItem(CLIENT_KEY, id);
  }
  return id;
}

function clientHeaders(): Record<string, string> {
  return { "X-Client-ID": clientId() };
}

async function handle(res: Response) {
  if (!res.ok) {
    let detail = "";
    try {
      const j = await res.json();
      detail = j.detail || JSON.stringify(j).slice(0, 140);
    } catch {
      detail = res.statusText;
    }
    throw new Error(detail);
  }
  return res.json();
}

export async function getJSON<T = any>(path: string, signal?: AbortSignal): Promise<T> {
  return fetch(`${API}${path}`, {
    signal,
    cache: "no-store",
    headers: clientHeaders(),
  }).then(handle);
}

export async function postJSON<T = any>(path: string, body?: any, method = "POST"): Promise<T> {
  return fetch(`${API}${path}`, {
    method,
    headers: { "Content-Type": "application/json", ...clientHeaders() },
    body: body === undefined ? undefined : JSON.stringify(body),
  }).then(handle);
}
