import { Suspense } from "react";
import SearchPage from "../../../components/legal/search-page";
export default function Page() { return <Suspense fallback={<p>Se pregătește căutarea…</p>}><SearchPage /></Suspense>; }
