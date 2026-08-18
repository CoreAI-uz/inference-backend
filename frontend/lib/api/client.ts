// Typed fetch wrapper. Same-origin /api (cookies included). Non-2xx → ApiError with
// the backend's uniform body {error, message, retry_after?, upgrade_hint?}.

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public retryAfter?: number,
    public upgradeHint?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(path, {
    credentials: "include",
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  });

  if (!resp.ok) {
    let body: Record<string, unknown> = {};
    try {
      body = await resp.json();
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(
      resp.status,
      (body.error as string) ?? "error",
      (body.message as string) ?? resp.statusText,
      body.retry_after as number | undefined,
      body.upgrade_hint as string | undefined,
    );
  }

  if (resp.status === 204) return undefined as T;
  return resp.json() as Promise<T>;
}
