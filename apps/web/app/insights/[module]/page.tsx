import { notFound } from "next/navigation";
import { Suspense } from "react";

import { InsightsDashboardView } from "../../../components/insights/insights-dashboard";
import { LoadingState } from "../../../components/ui/data-state";

const modules = new Set(["legal", "contracts", "documents", "notifications"]);

export default async function InsightsModulePage({ params }: { params: Promise<{ module: string }> }) {
  const { module } = await params;
  if (!modules.has(module)) notFound();
  return <Suspense fallback={<LoadingState label="Pregătim dashboardul modulului…" />}><InsightsDashboardView module={module} /></Suspense>;
}

