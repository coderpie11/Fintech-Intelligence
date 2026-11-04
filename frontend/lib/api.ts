export const API = "/bff/api/v1";

export type Env<T = any> = {
  value: T | null;
  status: string;
  note: string;
};

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
  return fetch(`${API}${path}`, { signal, cache: "no-store" }).then(handle);
}

export async function postJSON<T = any>(path: string, body?: any, method = "POST"): Promise<T> {
  return fetch(`${API}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  }).then(handle);
}
