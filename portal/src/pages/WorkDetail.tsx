import { useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, labelFor, CATALOGUES } from "../lib/api";

/**
 * Verovio incipit renderer.
 * Lazy by design: the toolkit is only imported, and the MEI only fetched, when
 * the work actually carries renderable notation (cnw:hasNotatedMusic). Rendered
 * SVG is memoised per record so re-visits do not re-engrave, the browser-side
 * counterpart of incipit_cache.py.
 */
const svgCache = new Map<string, string>();

function Incipit({ cnw }: { cnw: string }) {
  const [svg, setSvg] = useState<string | null>(svgCache.get(cnw) ?? null);
  const [err, setErr] = useState<string | null>(null);
  const done = useRef(false);

  useEffect(() => {
    if (done.current || svg) return;
    done.current = true;
    (async () => {
      try {
        const padded = cnw.padStart(4, "0");
        const mei = await fetch(`/mei/nielsen_cnw${padded}.xml`).then((r) => {
          if (!r.ok) throw new Error("MEI not found");
          return r.text();
        });
        const mod: any = await import("verovio");
        const toolkit = await (mod.default?.module
          ? new Promise((res) => mod.default.module.onRuntimeInitialized = () => res(new mod.default.toolkit()))
          : Promise.resolve(new mod.toolkit()));
        (toolkit as any).setOptions({
          // The panel is now full width, so the engraving is given the page width to match
          pageWidth: 2800, scale: 40, adjustPageHeight: true,
          header: "none", footer: "none",
        });
        (toolkit as any).loadData(mei);
        const out = (toolkit as any).renderToSVG(1);
        svgCache.set(cnw, out);
        setSvg(out);
      } catch (e: any) {
        setErr(e.message ?? "render failed");
      }
    })();
  }, [cnw, svg]);

  if (err) {
    console.warn(`Verovio could not render the incipit: ${err}`);
    return <p className="text-sm text-stone-500">Incipit not available.</p>;
  }
  if (!svg) return <p className="text-sm text-stone-500">Engraving notation…</p>;
  return <div className="overflow-x-auto bg-white border border-stone-200 rounded-lg p-3 w-full"
              dangerouslySetInnerHTML={{ __html: svg }} />;
}

/**
 * Incipit graphic supplied with the catalogue data. Most records carry the
 * first bars as an image rather than encoded notation, so this is what the
 * majority of works display. Images live in portal/public/incipits.
 */
function IncipitImage({ file, title }: { file: string; title: string }) {
  const [failed, setFailed] = useState(false);
  if (failed) {
    // The reader is told only that there is nothing to show. The cause, a
    // graphic the record names but the server does not hold, is a deployment
    // detail and goes to the console instead of into the page.
    return <p className="text-sm text-stone-500">Incipit not available.</p>;
  }
  return (
    <div className="bg-white border border-stone-200 rounded-lg p-3 w-full overflow-x-auto">
      <img src={`/incipits/${file}`} alt={`Opening bars of ${title}`}
           onError={() => {
             console.warn(`Incipit graphic missing: /incipits/${file}. ` +
               `Copy the catalogue's incipit folder into portal/public/incipits.`);
             setFailed(true);
           }}
           className="max-w-full h-auto" />
    </div>
  );
}

function Field({ label, value }: { label: string; value?: string | null }) {
  if (!value) return null;
  return (
    <div className="py-2 border-b border-stone-100 flex gap-4">
      <dt className="text-sm text-stone-500 w-40 shrink-0">{label}</dt>
      <dd className="text-sm text-stone-900">{value}</dd>
    </div>
  );
}

export default function WorkDetail() {
  const { cnw = "" } = useParams();
  // Numbering restarts in every catalogue, so the code travels with the number.
  const [params] = useSearchParams();
  const catalogue = params.get("catalogue") ?? undefined;
  const { data, isLoading, isError } = useQuery({
    queryKey: ["work", cnw, catalogue ?? ""], queryFn: () => api.work(cnw, catalogue),
  });
  const { data: composers } = useQuery({ queryKey: ["composers"], queryFn: api.composers });

  if (isLoading) return <p className="text-stone-500 text-sm">Loading...</p>;
  if (isError || !data) return <p className="text-red-700 text-sm">Work not found.</p>;

  const links = composers?.find((c) => c.name?.replace(/[\[\]]/g, "") === data.composer)
    ?.external_links ?? [];

  return (
    <article>
      <Link to="/" className="text-sm text-stone-500 hover:text-stone-800">&larr; All works</Link>
      <h1 className="text-2xl font-semibold text-stone-900 mt-2">{data.title}</h1>
      <p className="text-stone-500 text-sm mt-1">
        {`${data.catalogue ?? ""} ${data.cnw ?? ""}`.trim()}
        {data.opus ? ` · Op. ${data.opus}` : ""}
        {data.catalogue && CATALOGUES[data.catalogue]
          ? ` · ${CATALOGUES[data.catalogue]}` : ""}
      </p>

      {/* Catalogue record, then notation full width below it. Participants in
          the usability study consistently reported the notation being cramped
          and cut off when it sat in a narrow side column. */}
      <div className="grid lg:grid-cols-2 gap-6 mt-5">
        <section>
          <h2 className="text-sm font-semibold text-stone-700 uppercase tracking-wide">Catalogue record</h2>
          <dl className="mt-2">
            <Field label="Composer" value={data.composer} />
            <Field label="Composed" value={data.created} />
            <Field label="Key" value={data.key} />
            <Field label="Tempo" value={data.tempo} />
            <Field label="Metre" value={data.meter} />
            <Field label="Genre" value={data.genres.join(", ")} />
            <Field label="Scoring" value={data.scoring.join(", ")} />
            <Field label="Text incipit" value={data.incipit_text} />
          </dl>
        </section>

        <section>
          {links.length > 0 && (
            <>
              <h2 className="text-sm font-semibold text-stone-700 uppercase tracking-wide">
                External identifiers
              </h2>
              <div className="flex flex-wrap gap-2 mt-2">
                {links.map((u) => (
                  <a key={u} href={u} target="_blank" rel="noreferrer"
                     className="text-sm border border-stone-300 rounded-full px-4 min-h-11 inline-flex
                                items-center hover:bg-stone-100 focus:outline-none focus:ring-2 focus:ring-stone-700">
                    {labelFor(u)} ↗
                  </a>
                ))}
              </div>
              <p className="text-xs text-stone-500 mt-2">
                Composer-level links are verified via VIAF. Work-level matches are
                stored separately with a confidence score (see Evaluation).
              </p>
            </>
          )}

          {data.editorial_notes.length > 0 && (
            <>
              <h2 className="text-sm font-semibold text-stone-700 uppercase tracking-wide mt-5">
                Editorial notes
              </h2>
              {data.editorial_notes.map((n, i) => (
                <p key={i} className="text-sm text-stone-700 mt-2">{n}</p>
              ))}
            </>
          )}
        </section>
      </div>

      <section className="mt-8">
        <h2 className="text-sm font-semibold text-stone-700 uppercase tracking-wide">Incipit</h2>
        <p className="text-xs text-stone-500 mt-1">
          The opening bars, as recorded by the catalogue to identify the work.
          Full scores are not part of the published dataset.
        </p>
        <div className="mt-2">
          {data.has_notated_music ? (
            <Incipit cnw={data.cnw ?? ""} />
          ) : data.incipit_image ? (
            <IncipitImage file={data.incipit_image} title={data.title ?? "this work"} />
          ) : (
            <p className="text-sm text-stone-500">Incipit not available.</p>
          )}
        </div>
      </section>
    </article>
  );
}