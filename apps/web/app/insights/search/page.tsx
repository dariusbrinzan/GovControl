import { Suspense } from "react";

import { InsightsSearchView } from "../../../components/insights/insights-search";
import { LoadingState } from "../../../components/ui/data-state";

export default function InsightsSearchPage() {
  return <Suspense fallback={<LoadingState label="Pregătim căutarea unificată…" />}><InsightsSearchView /></Suspense>;
}

