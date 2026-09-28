import { Suspense } from "react";

import { InsightsDashboardView } from "../../components/insights/insights-dashboard";
import { LoadingState } from "../../components/ui/data-state";

export default function InsightsPage() {
  return <Suspense fallback={<LoadingState label="Pregătim dashboardul executiv…" />}><InsightsDashboardView /></Suspense>;
}

