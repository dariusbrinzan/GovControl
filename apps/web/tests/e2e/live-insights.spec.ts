import { expect, test } from "@playwright/test";
import { writeFile } from "node:fs/promises";

type SearchPage = {
  items: Array<{ identifier: string | null; display_label: string | null }>;
  total: number;
};

test("GovInsights rulează dashboard, proiecție, raport și export prin Gateway", async ({
  page,
  request,
}) => {
  const origin = "http://localhost:8080";
  const login = await request.post(`${origin}/auth/local/login`, {
    headers: { Origin: "http://localhost:3000" },
  });
  expect(login.status()).toBe(200);
  const { csrf_token: csrf } = (await login.json()) as { csrf_token: string };
  const storageState = await request.storageState();
  await page.context().addCookies(storageState.cookies);

  await page.goto("/insights");
  await expect(
    page.getByRole("heading", { name: "Dashboard executiv instituțional" }),
  ).toBeVisible();
  await expect(page.getByText("Proiecții sincronizate")).toBeVisible();
  const dashboardTabs = page.getByRole("navigation", { name: "Dashboarduri GovInsights" });
  await dashboardTabs.getByRole("link", { name: "GovLegal" }).click();
  await expect(page.getByRole("heading", { name: "Dashboard GovLegal" })).toBeVisible();
  await dashboardTabs.getByRole("link", { name: "GovContracts" }).click();
  await expect(page.getByRole("heading", { name: "Dashboard GovContracts" })).toBeVisible();

  const normalDashboard = await request.get(
    `${origin}/api/v1/insights/dashboards/executive`,
  );
  const forgedDashboard = await request.get(
    `${origin}/api/v1/insights/dashboards/executive`,
    { headers: { "X-Tenant-ID": "00000000-0000-0000-0000-000000000099" } },
  );
  expect(normalDashboard.status()).toBe(200);
  expect(forgedDashboard.status()).toBe(200);
  const normalPayload = (await normalDashboard.json()) as {
    module: string | null;
    total: number;
  };
  const forgedPayload = (await forgedDashboard.json()) as {
    module: string | null;
    total: number;
  };
  expect(normalPayload.module).toBeNull();
  expect(forgedPayload.module).toBeNull();
  expect(normalPayload.total).toBeGreaterThan(0);
  expect(forgedPayload.total).toBeGreaterThan(0);

  const contractsResponse = await request.get(
    `${origin}/api/v1/govcontracts/contracts?limit=1`,
  );
  expect(contractsResponse.status()).toBe(200);
  const contracts = (await contractsResponse.json()) as Array<{
    id: string;
    contract_number: string;
    title: string;
  }>;
  const contract = contracts[0];
  expect(contract).toBeTruthy();
  const marker = `Insights E2E ${Date.now()}`;
  expect(
    (
      await request.patch(`${origin}/api/v1/govcontracts/contracts/${contract.id}`, {
        headers: { "X-CSRF-Token": csrf },
        data: { title: marker },
      })
    ).status(),
  ).toBe(200);
  await expect
    .poll(
      async () => {
        const response = await request.get(
          `${origin}/api/v1/insights/search?q=${encodeURIComponent(marker)}&module=contracts`,
        );
        if (!response.ok()) return false;
        const result = (await response.json()) as SearchPage;
        return result.items.some((item) => item.display_label === marker);
      },
      { timeout: 30_000 },
    )
    .toBe(true);
  expect(
    (
      await request.patch(`${origin}/api/v1/govcontracts/contracts/${contract.id}`, {
        headers: { "X-CSRF-Token": csrf },
        data: { title: contract.title },
      })
    ).status(),
  ).toBe(200);

  const reportResponse = await request.post(`${origin}/api/v1/insights/reports`, {
    headers: { "X-CSRF-Token": csrf },
    data: {
      name: `E2E GovInsights ${Date.now()}`,
      description: "Raport temporar E2E",
      resource_type: "contract",
      filters: { module: "contracts" },
      columns: ["identifier", "display_label", "status", "currency"],
      sort: [{ column: "identifier", direction: "asc" }],
      shared_with_roles: [],
    },
  });
  expect(reportResponse.status()).toBe(201);
  const report = (await reportResponse.json()) as { id: string };
  const runResponse = await request.post(
    `${origin}/api/v1/insights/reports/${report.id}/runs`,
    {
      headers: { "X-CSRF-Token": csrf },
      data: { export_format: "csv" },
    },
  );
  expect(runResponse.status()).toBe(202);
  const run = (await runResponse.json()) as { id: string };

  let exportId = "";
  await expect
    .poll(
      async () => {
        const response = await request.get(`${origin}/api/v1/insights/exports`);
        if (!response.ok()) return "unavailable";
        const items = (await response.json()) as Array<{
          id: string;
          run_id: string;
          status: string;
        }>;
        const artifact = items.find((item) => item.run_id === run.id);
        exportId = artifact?.id ?? "";
        return artifact?.status ?? "missing";
      },
      { timeout: 30_000 },
    )
    .toBe("SUCCEEDED");
  const download = await request.get(
    `${origin}/api/v1/insights/exports/${exportId}/download`,
  );
  expect(download.status()).toBe(200);
  expect(await download.text()).toContain(contract.contract_number);
  expect(
    (
      await request.get(
        `${origin}/api/v1/insights/exports/00000000-0000-4000-8000-000000000099/download`,
      )
    ).status(),
  ).toBe(404);

  await writeFile(
    "/tmp/govcontrol-insights-e2e.json",
    JSON.stringify({ report_ids: [report.id], run_ids: [run.id], export_ids: [exportId] }),
  );
  expect(
    (
      await request.delete(`${origin}/api/v1/insights/reports/${report.id}`, {
        headers: { "X-CSRF-Token": csrf },
      })
    ).status(),
  ).toBe(204);
  expect(
    (
      await request.post(`${origin}/auth/logout`, {
        headers: { "X-CSRF-Token": csrf },
      })
    ).status(),
  ).toBe(204);
  expect((await request.get(`${origin}/auth/session`)).status()).toBe(401);
});
