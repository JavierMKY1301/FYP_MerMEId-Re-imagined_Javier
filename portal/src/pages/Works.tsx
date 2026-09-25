import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, WorkSummary, compareCnw, normaliseNumber, CATALOGUES } from "../lib/api";

/**
 * Catalogue browser.
 *
 * Design decisions taken after evaluating against the full 446-record corpus
 * and the participant study:
 *
 *  - The whole catalogue is fetched once and held in memory. Filtering,
 *    searching, sorting and paging then happen client side, so typing in the
 *    search box costs nothing. Requesting per keystroke made the portal feel
 *    slow once the corpus grew beyond the 11-record sample.
 *  - Facet values come from /facets, which reads them from the graph. A
 *    hardcoded list cannot offer values the data does not contain, and cannot
 *    grow with the corpus.
 *  - Genre leads, because it covers the catalogue (343 works are vocal music),
 *    while key is present on only 19 of 446 works. Facets were chosen on
 *    measured coverage rather than on what looked plausible in a small sample.
 *  - Controls are at least 44 px tall, after a participant asked for larger
 *    targets. This also satisfies WCAG 2.2 target size (2.5.8).
 */

type SortKey = "cnw" | "cnw_desc" | "title" | "title_desc" | "key" | "meter" | "catalogue";

const SORTS: { value: SortKey; label: string }[] = [
  { value: "cnw", label: "Catalogue number (low to high)" },
  { value: "cnw_desc", label: "Catalogue number (high to low)" },
  { value: "catalogue", label: "Catalogue, then number" },
  { value: "title", label: "Title (A to Z)" },
  { value: "title_desc", label: "Title (Z to A)" },
  { value: "key", label: "Key" },
  { value: "meter", label: "Metre" },
];

const PAGE_SIZES = [10, 20, 50, 100];

const selectClass =
  "border border-stone-300 rounded-md px-3 py-2 text-sm bg-white min-h-11 " +
  "focus:outline-none focus:ring-2 focus:ring-stone-700";

export default function Works() {
  const [q, setQ] = useState("");
  const [catalogue, setCatalogue] = useState("");
  const [genre, setGenre] = useState("");
  const [key, setKey] = useState("");
  const [meter, setMeter] = useState("");
  const [sort, setSort] = useState<SortKey>("cnw");
  const [pageSize, setPageSize] = useState(20);
  const [page, setPage] = useState(1);

  const works = useQuery({ queryKey: ["allWorks"], queryFn: api.allWorks });
  const facets = useQuery({ queryKey: ["facets"], queryFn: api.facets });

  const all: WorkSummary[] = works.data ?? [];

  // Filter, search and sort. Recomputed only when an input actually changes.
  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const num = needle ? normaliseNumber(needle) : "";
    let out = all.filter((w) => {
      if (catalogue && w.catalogue !== catalogue) return false;
      if (genre && !w.genres.includes(genre)) return false;
      if (key && w.key !== key) return false;
      if (meter && w.meter !== meter) return false;
      if (!needle) return true;
      const title = (w.title ?? "").toLowerCase();
      const cnw = normaliseNumber(w.cnw ?? "");
      return title.includes(needle) || (!!num && (cnw === num || cnw.includes(num)));
    });
    const byText = (a: string | null, b: string | null) =>
      (a ?? "\uffff").localeCompare(b ?? "\uffff");
    const byCat = (a: WorkSummary, b: WorkSummary) =>
      (a.catalogue ?? "\uffff").localeCompare(b.catalogue ?? "\uffff");
    out = [...out].sort((a, b) => {
      switch (sort) {
        case "catalogue": return byCat(a, b) || compareCnw(a.cnw, b.cnw);
        case "cnw_desc": return compareCnw(b.cnw, a.cnw);
        case "title": return byText(a.title, b.title);
        case "title_desc": return byText(b.title, a.title);
        case "key": return byText(a.key, b.key) || compareCnw(a.cnw, b.cnw);
        case "meter": return byText(a.meter, b.meter) || compareCnw(a.cnw, b.cnw);
        default: return compareCnw(a.cnw, b.cnw);
      }
    });
    return out;
  }, [all, q, catalogue, genre, key, meter, sort]);

  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize));
  const current = Math.min(page, pageCount);
  const shown = rows.slice((current - 1) * pageSize, current * pageSize);

  // Any change to the result set returns the reader to the first page.
  const reset = <T,>(setter: (v: T) => void) => (v: T) => { setter(v); setPage(1); };

  const clearAll = () => {
    setQ(""); setCatalogue(""); setGenre(""); setKey(""); setMeter(""); setPage(1);
  };
  const filtered = !!(q || catalogue || genre || key || meter);

  return (
    <div>
      <h1 className="text-2xl font-semibold text-stone-900">Works</h1>
      <p className="text-stone-600 text-sm mt-1">
        Browse four thematic catalogues together: Carl Nielsen, Niels W. Gade,
        J.P.E. Hartmann and J.A. Scheibe. Filtering by genre, key or metre across
        every work, in every catalogue, is a cross-cutting query that the original
        per-file XML cannot answer without external tooling.
      </p>

      {/* Search and facets */}
      <div className="mt-4 flex flex-wrap gap-3 items-end">
        <div>
          <label htmlFor="q" className="block text-xs text-stone-500 mb-1">
            Search title or catalogue number
          </label>
          <input
            id="q" value={q} onChange={(e) => reset(setQ)(e.target.value)}
            placeholder="e.g. Summer Song or CNW 129"
            className={`${selectClass} w-72`}
          />
        </div>

        <div>
          <label htmlFor="catalogue" className="block text-xs text-stone-500 mb-1">Catalogue</label>
          <select id="catalogue" value={catalogue}
                  onChange={(e) => reset(setCatalogue)(e.target.value)}
                  className={selectClass}>
            <option value="">All catalogues</option>
            {facets.data?.catalogue.map((f) => (
              <option key={f.value} value={f.value}>
                {CATALOGUES[f.value] ?? f.value} ({f.count})
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="genre" className="block text-xs text-stone-500 mb-1">Genre</label>
          <select id="genre" value={genre} onChange={(e) => reset(setGenre)(e.target.value)}
                  className={selectClass}>
            <option value="">All genres</option>
            {facets.data?.genre.map((f) => (
              <option key={f.value} value={f.value}>{f.value} ({f.count})</option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="key" className="block text-xs text-stone-500 mb-1">Key</label>
          <select id="key" value={key} onChange={(e) => reset(setKey)(e.target.value)}
                  className={selectClass}>
            <option value="">All keys</option>
            {facets.data?.key.map((f) => (
              <option key={f.value} value={f.value}>{f.value} ({f.count})</option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="meter" className="block text-xs text-stone-500 mb-1">Metre</label>
          <select id="meter" value={meter} onChange={(e) => reset(setMeter)(e.target.value)}
                  className={selectClass}>
            <option value="">All metres</option>
            {facets.data?.meter.map((f) => (
              <option key={f.value} value={f.value}>{f.value} ({f.count})</option>
            ))}
          </select>
        </div>

        {filtered && (
          <button onClick={clearAll}
            className="min-h-11 px-4 rounded-md border border-stone-300 text-sm text-stone-700 hover:bg-stone-100">
            Clear filters
          </button>
        )}
      </div>

      {/* Sort, page size and result count */}
      <div className="mt-4 flex flex-wrap gap-3 items-end justify-between">
        <div className="flex flex-wrap gap-3 items-end">
          <div>
            <label htmlFor="sort" className="block text-xs text-stone-500 mb-1">Sort by</label>
            <select id="sort" value={sort}
                    onChange={(e) => reset(setSort)(e.target.value as SortKey)}
                    className={selectClass}>
              {SORTS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="size" className="block text-xs text-stone-500 mb-1">Per page</label>
            <select id="size" value={pageSize}
                    onChange={(e) => reset(setPageSize)(Number(e.target.value))}
                    className={selectClass}>
              {PAGE_SIZES.map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </div>
        </div>
        <p className="text-sm text-stone-600 min-h-11 flex items-end pb-2" aria-live="polite">
          {works.isLoading ? "Loading catalogue…"
            : `${rows.length} work${rows.length === 1 ? "" : "s"}${filtered ? " match" : ""}`}
          {rows.length > 0 && ` · page ${current} of ${pageCount}`}
        </p>
      </div>

      {works.isError && (
        <p className="mt-6 text-red-700 text-sm">
          Could not reach the API. Start it with:
          <code className="bg-stone-100 px-1 mx-1 rounded">uvicorn api.main:app --port 8000</code>
        </p>
      )}

      {!works.isLoading && rows.length === 0 && (
        <p className="mt-6 text-stone-600 text-sm">
          Nothing matches those filters. Try clearing one, or search by catalogue
          number such as 129. Numbering restarts in each catalogue, so the same
          number can appear more than once.
        </p>
      )}

      {/* Results */}
      <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {shown.map((w) => (
          <Link key={w.iri}
            to={w.cnw
              ? `/works/${encodeURIComponent(w.cnw)}` +
                (w.catalogue ? `?catalogue=${encodeURIComponent(w.catalogue)}` : "")
              : "#"}
            className="block border border-stone-200 bg-white rounded-lg p-4 hover:shadow-md
                       focus:outline-none focus:ring-2 focus:ring-stone-700 transition">
            <div className="text-xs text-stone-500">
              {w.cnw ? `${w.catalogue ?? ""} ${w.cnw}`.trim() : "no catalogue number"}
            </div>
            <div className="font-medium text-stone-900 mt-1">{w.title ?? "Untitled"}</div>
            <div className="text-sm text-stone-600 mt-1">
              {[w.key, w.meter].filter(Boolean).join(" · ")}
            </div>
            {w.genres.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {w.genres.slice(0, 3).map((g) => (
                  <span key={g} className="text-xs text-stone-600 border border-stone-200 rounded-full px-2 py-0.5">
                    {g}
                  </span>
                ))}
              </div>
            )}
          </Link>
        ))}
      </div>

      {/* Pagination */}
      {pageCount > 1 && (
        <nav className="mt-6 flex flex-wrap items-center justify-center gap-2" aria-label="Pagination">
          <PageButton label="Previous" disabled={current === 1}
                      onClick={() => setPage(current - 1)} />
          {pageNumbers(current, pageCount).map((n, i) =>
            n === "gap" ? (
              <span key={`gap${i}`} className="px-2 text-stone-400">…</span>
            ) : (
              <button key={n} onClick={() => setPage(n)}
                aria-current={n === current ? "page" : undefined}
                className={`min-h-11 min-w-11 px-3 rounded-md border text-sm ${
                  n === current
                    ? "bg-stone-800 text-white border-stone-800"
                    : "border-stone-300 text-stone-700 hover:bg-stone-100"}`}>
                {n}
              </button>
            )
          )}
          <PageButton label="Next" disabled={current === pageCount}
                      onClick={() => setPage(current + 1)} />
        </nav>
      )}

      <p className="mt-5 text-xs text-stone-500">
        Works without a catalogue number are listed but not addressable by number,
        a documented edge case (E04).
      </p>
    </div>
  );
}

function PageButton({ label, disabled, onClick }:
  { label: string; disabled: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick} disabled={disabled}
      className="min-h-11 px-4 rounded-md border border-stone-300 text-sm text-stone-700
                 hover:bg-stone-100 disabled:opacity-40 disabled:cursor-not-allowed">
      {label}
    </button>
  );
}

/** A windowed page list: 1 … 4 5 [6] 7 8 … 23 */
function pageNumbers(current: number, total: number): (number | "gap")[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const out: (number | "gap")[] = [1];
  const from = Math.max(2, current - 1);
  const to = Math.min(total - 1, current + 1);
  if (from > 2) out.push("gap");
  for (let n = from; n <= to; n++) out.push(n);
  if (to < total - 1) out.push("gap");
  out.push(total);
  return out;
}
