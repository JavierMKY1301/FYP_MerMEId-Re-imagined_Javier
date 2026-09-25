import { Link, Route, Routes, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "./lib/api";
import Works from "./pages/Works";
import WorkDetail from "./pages/WorkDetail";
import Dashboard from "./pages/Dashboard";

function Nav() {
  const { pathname } = useLocation();
  const { data: health } = useQuery({ queryKey: ["health"], queryFn: api.health });
  const tab = (to: string, label: string) => {
    const active = to === "/" ? pathname === "/" : pathname.startsWith(to);
    return (
      <Link to={to} className={`px-3 py-2 rounded-md text-sm font-medium ${
        active ? "bg-white text-stone-900 shadow-sm" : "text-stone-200 hover:text-white"}`}>
        {label}
      </Link>
    );
  };
  return (
    <header className="bg-stone-800">
      <div className="max-w-6xl mx-auto px-4 py-3 flex items-center gap-4 flex-wrap">
        <div className="mr-auto">
          <div className="text-white font-semibold">MerMEId Re-imagined</div>
          <div className="text-stone-400 text-xs">
            Danish Centre for Music Editing catalogues - Linked Data portal
          </div>
        </div>
        {tab("/", "Works")}
        {tab("/evaluation", "Evaluation")}
        {health && (
          <span className="text-xs text-stone-400 ml-2 border border-stone-600 rounded px-2 py-1">
            {health.triples.toLocaleString()} triples . {health.engine}
          </span>
        )}
      </div>
    </header>
  );
}

export default function App() {
  return (
    <div className="min-h-screen flex flex-col">
      <Nav />
      <main className="flex-1 max-w-6xl w-full mx-auto px-4 py-6">
        <Routes>
          <Route path="/" element={<Works />} />
          <Route path="/works/:cnw" element={<WorkDetail />} />
          <Route path="/evaluation" element={<Dashboard />} />
        </Routes>
      </main>
      <footer className="border-t border-stone-200 text-xs text-stone-500 py-4">
        <div className="max-w-6xl mx-auto px-4">
          Data: thematic catalogues of Carl Nielsen, Niels W. Gade, J.P.E. Hartmann and
          J.A. Scheibe, created 2010-2020 by the Danish Centre for Music Editing,
          Royal Danish Library, and released as MEI under CC0. CM3070 project.
        </div>
      </footer>
    </div>
  );
}
