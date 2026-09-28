import { expect, test, type Page } from "@playwright/test";

const user = {
  id: "00000000-0000-4000-8000-000000000001",
  tenant_id: "00000000-0000-4000-8000-000000000002",
  department_id: null,
  email: "analyst@govcontrol.local",
  display_name: "Analist GovInsights",
  roles: ["auditor"],
  permissions: [
    "insights.read",
    "insights.search",
    "insights.report",
    "insights.export",
    "insights.audit",
  ],
};

const dashboard = {
  module: null,
  total: 12,
  by_status: [
    { key: "ACTIVE", count: 8 },
    { key: "OVERDUE", count: 4 },
  ],
  by_type: [
    { key: "contract", count: 7 },
    { key: "obligation", count: 5 },
  ],
  workload_by_department: [{ key: "Direcția juridică", count: 12 }],
  workload_by_responsible: [{ key: "Funcționar test", count: 12 }],
  financial_exposure: [
    { category: "contract", currency: "RON", amount: "125000.00" },
  ],
  monthly_trend: [
    { month: "2026-08", count: 5 },
    { month: "2026-09", count: 7 },
  ],
  period_total: 7,
  previous_period_total: 5,
  period_change_percent: 40,
  overdue: 4,
  due_soon_7: 2,
  due_soon_30: 3,
  due_soon_60: 4,
  due_soon_90: 5,
  projection_version: 42,
  last_updated_at: "2026-09-27T12:00:00Z",
  stale: false,
};

async function mockSession(page: Page, permissions = user.permissions) {
  await page.route("**/auth/config", (route) =>
    route.fulfill({ json: { mode: "local", login_url: "/auth/login" } }),
  );
  await page.route("**/auth/session", (route) =>
    route.fulfill({
      json: {
        user: { ...user, permissions },
        csrf_token: "csrf-token",
        expires_at: "2026-09-28T00:00:00Z",
        auth_method: "local",
      },
    }),
  );
}

test("GovInsights oferă dashboard, filtre URL și căutare filtrată", async ({ page }) => {
  await mockSession(page);
  await page.route("**/api/v1/insights/dashboards/**", (route) =>
    route.fulfill({ json: dashboard }),
  );
  await page.route("**/api/v1/insights/search?**", (route) =>
    route.fulfill({
      json: {
        items: [
          {
            id: "00000000-0000-4000-8000-000000000010",
            module: "contracts",
            resource_type: "contract",
            source_id: "00000000-0000-4000-8000-000000000011",
            identifier: "CTR-2026-10",
            display_label: "Servicii publice",
            status: "ACTIVE",
            source_url: "/contracts/00000000-0000-4000-8000-000000000011",
            rank: 0,
            updated_at: "2026-09-27T12:00:00Z",
          },
        ],
        total: 1,
        limit: 25,
        offset: 0,
      },
    }),
  );

  await page.goto("/insights");
  await expect(
    page.getByRole("heading", { name: "Dashboard executiv instituțional" }),
  ).toBeVisible();
  await expect(page.getByText("Proiecții sincronizate")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Evoluție lunară" })).toBeVisible();
  await expect(page.getByText("+40% față de perioada anterioară")).toBeVisible();

  await page.getByLabel("De la").fill("2026-09-01");
  await page.getByLabel("Până la").fill("2026-09-30");
  await page.getByRole("button", { name: "Aplică perioada" }).click();
  await expect(page).toHaveURL(/date_from=2026-09-01.*date_to=2026-09-30/);

  await page.goto("/insights/search?module=contracts&status=ACTIVE&limit=25");
  await expect(page.getByText("CTR-2026-10")).toBeVisible();
  await expect(page.getByText("1 rezultate tenant-scoped")).toBeVisible();
});

test("GovInsights salvează un raport controlat și afișează forbidden", async ({ page }) => {
  await mockSession(page);
  let reports: Array<Record<string, unknown>> = [];
  await page.route("**/api/v1/insights/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname.endsWith("/metadata")) {
      return route.fulfill({
        json: {
          modules: ["contracts", "legal"],
          report_columns: ["identifier", "status", "occurred_at", "due_at"],
          report_resource_types: ["contract", "case"],
        },
      });
    }
    if (url.pathname.endsWith("/runs")) return route.fulfill({ json: [] });
    if (url.pathname.endsWith("/reports") && request.method() === "POST") {
      const input = request.postDataJSON() as Record<string, unknown>;
      reports = [
        {
          ...input,
          id: "00000000-0000-4000-8000-000000000020",
          owner_user_id: user.id,
          created_at: "2026-09-27T12:00:00Z",
          updated_at: "2026-09-27T12:00:00Z",
        },
      ];
      return route.fulfill({ status: 201, json: reports[0] });
    }
    if (url.pathname.endsWith("/reports")) return route.fulfill({ json: reports });
    return route.fulfill({ status: 404, json: { detail: "Not mocked" } });
  });

  await page.goto("/insights/reports");
  await page.getByLabel("Nume raport").fill("Contracte active");
  await page.locator(".report-filter-grid select").first().selectOption("contracts");
  await page.locator('.report-filter-grid input[placeholder="Ex. ACTIVE"]').fill("active");
  await page.getByRole("button", { name: "Salvează raportul" }).click();
  await expect(page.getByRole("heading", { name: "Contracte active" })).toBeVisible();

  await page.unrouteAll({ behavior: "wait" });
  await mockSession(page, []);
  await page.goto("/insights");
  await expect(
    page.getByText("Rolul curent nu are permisiunea insights.read."),
  ).toBeVisible();
});
