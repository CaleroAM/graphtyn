export type GraphtynOptions = { baseUrl?: string; token?: string };

export class GraphtynClient {
  readonly baseUrl: string;
  readonly token?: string;
  constructor(options: GraphtynOptions = {}) {
    this.baseUrl = (options.baseUrl || "http://127.0.0.1:9210").replace(/\/$/, "");
    this.token = options.token;
  }
  private async request(path: string, body?: unknown, method = "POST") {
    const response = await fetch(`${this.baseUrl}${path}`, {
      method, headers: { "Content-Type": "application/json", ...(this.token ? { Authorization: `Bearer ${this.token}` } : {}) },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `Graphtyn HTTP ${response.status}`);
    return data;
  }
  ingestTurn(payload: unknown) { return this.request("/api/v1/memory/ingest", payload); }
  context(payload: unknown) { return this.request("/api/v1/context", payload); }
  discoverImports(payload: unknown = {}) { return this.request("/api/v1/imports/discover", payload); }
  startImport(payload: unknown) { return this.request("/api/v1/imports", payload); }
  importStatus(jobId: string) { return this.request(`/api/v1/imports/${encodeURIComponent(jobId)}`, undefined, "GET"); }
  event(name: string, payload: unknown) { return this.request(`/api/v1/events/${encodeURIComponent(name)}`, payload); }
}
