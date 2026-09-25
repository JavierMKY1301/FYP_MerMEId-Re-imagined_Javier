// Typed client for the FastAPI REST layer (Expose). One function per endpoint.
export interface WorkSummary {
  iri: string;
  catalogue: string | null;
  cnw: string | null;
  title: string | null;
  key: string | null;
  meter: string | null;
  genres: string[];
  incipit_image: string | null;
}
export interface WorkDetail extends WorkSummary {
  opus: string | null; composer: string | null; created: string | null;
  tempo: string | null; incipit_text: string | null;
  has_notated_music: boolean | null; scoring: string[]; editorial_notes: string[];
}
export interface Composer { iri: string; name: string | null; external_links: string[]; }
export interface Health { status: string; engine: string; triples: number; works_cached: number; }
export interface FacetValue { value: string; count: number; }
export interface Facets {
  catalogue: FacetValue[]; genre: FacetValue[]; key: FacetValue[]; meter: FacetValue[];
}

/** Human-readable catalogue names, keyed by the code stored in the graph. */
export const CATALOGUES: Record<string, string> = {
  CNW: "Carl Nielsen (CNW)",
  NWGW: "Niels W. Gade (NWGW)",
  HartW: "J.P.E. Hartmann (HartW)",
  SchW: "J.A. Scheibe (SchW)",
};

const BASE = import.meta.env.DEV ? "/api" : "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json() as Promise<T>;
}

export const api = {
  health: () => get<Health>("/health"),
  /**
   * The whole catalogue in one request. At 446 works this is roughly 100 kB,
   * so the portal fetches once on load and then filters, sorts and pages in
   * the browser. Per-keystroke requests against the server were the cause of
   * the sluggish search reported during usability testing.
   */
  allWorks: async (): Promise<WorkSummary[]> => {
    // One request for the whole corpus, then page only if the catalogue has
    // outgrown a single response. X-Total-Count reports the size before paging.
    const PAGE = 5000;
    const r = await fetch(`${BASE}/works?limit=${PAGE}&offset=0`);
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    const first = (await r.json()) as WorkSummary[];
    const total = Number(r.headers.get("X-Total-Count") ?? first.length);
    if (total <= first.length) return first;
    const rest: WorkSummary[] = [];
    for (let offset = first.length; offset < total; offset += PAGE) {
      rest.push(...(await get<WorkSummary[]>(`/works?limit=${PAGE}&offset=${offset}`)));
    }
    return [...first, ...rest];
  },
  work: (cnw: string, catalogue?: string) =>
    get<WorkDetail>(`/works/${encodeURIComponent(cnw)}` +
      (catalogue ? `?catalogue=${encodeURIComponent(catalogue)}` : "")),
  facets: () => get<Facets>("/facets"),
  composers: () => get<Composer[]>("/composers"),
};

// External identifier links are stored as full IRIs; label them for display.
export function labelFor(url: string): string {
  if (url.includes("viaf.org")) return "VIAF";
  if (url.includes("wikidata")) return "Wikidata";
  if (url.includes("musicbrainz")) return "MusicBrainz";
  if (url.includes("imslp")) return "IMSLP";
  return "External";
}

/**
 * Catalogue order. Plain string comparison puts CNW 10 before CNW 2, and
 * collection entries such as "Coll. 18" have no numeric position at all, so
 * numbered works sort numerically and everything else follows alphabetically.
 */
export function compareCnw(a: string | null, b: string | null): number {
  const parse = (v: string | null) => {
    const s = (v ?? "").trim();
    const m = s.match(/^(\d+)/);
    return m ? { num: true, n: parseInt(m[1], 10), s } : { num: false, n: 0, s };
  };
  const x = parse(a), y = parse(b);
  if (x.num && y.num) return x.n - y.n || x.s.localeCompare(y.s);
  if (x.num !== y.num) return x.num ? -1 : 1;
  return x.s.localeCompare(y.s);
}

/** "CNW 129", "cnw129" and "129" should all reach the same work. */
export function normaliseNumber(term: string): string {
  const t = term.toLowerCase().replace(/[^a-z0-9]/g, "").replace(/^cnw/, "");
  return t.replace(/^0+/, "") || t;
}