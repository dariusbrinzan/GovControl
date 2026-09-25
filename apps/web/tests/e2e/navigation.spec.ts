import { expect, test } from "@playwright/test";

test("shell-ul instituțional și conectarea sunt accesibile", async ({ page }) => {
  await page.goto("/legal");
  await expect(page.getByRole("heading", { name: "Panou de control juridic" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Navigare GovLegal" })).toBeVisible();
  await expect(page.getByRole("dialog", { name: "Conectează spațiul de lucru" })).toBeVisible();
  await expect(page.getByLabel("DEV_AUTH_TOKEN")).toBeFocused();
});

test("navigarea deschide registrul de obligații", async ({ page }) => {
  await page.route("**/api/v1/auth/me", (route) => route.fulfill({ json: {
    id: "00000000-0000-0000-0000-000000000001", tenant_id: "00000000-0000-0000-0000-000000000002",
    department_id: null, email: "test@govcontrol.local", display_name: "Test User",
    roles: ["legal_officer"], permissions: ["legal.manage", "legal.report"],
  } }));
  await page.goto("/");
  await page.evaluate(() => window.localStorage.setItem("govcontrol.dev-token", "test-token"));
  await page.goto("/legal");
  await expect(page.getByRole("button", { name: /Test User/ })).toBeVisible();
  await page.getByRole("link", { name: "Obligații", exact: true }).click();
  await expect(page).toHaveURL(/\/legal\/obligations$/);
  await expect(page.getByRole("heading", { name: "Obligații instituționale" })).toBeVisible();
});

test("GovContracts afișează dashboard-ul și registrul din serviciul separat", async ({ page }) => {
  const browserErrors: string[] = [];
  page.on("pageerror", (error) => browserErrors.push(error.message));
  await page.route("**/api/v1/auth/me", (route) => route.fulfill({ json: {
    id: "00000000-0000-0000-0000-000000000001",
    tenant_id: "00000000-0000-0000-0000-000000000002",
    department_id: null,
    email: "contracts@govcontrol.local",
    display_name: "Manager Contracte",
    roles: ["contracts_manager"],
    permissions: ["contracts.manage", "contracts.report"],
  } }));
  await page.route("http://127.0.0.1:8010/api/v1/contracts**", (route) => {
    if (route.request().url().endsWith("/dashboard")) {
      return route.fulfill({ json: {
        total_contracts: 1,
        active_contracts: 1,
        expiring_within_30_days: 0,
        total_active_value: "250000.00",
        status_counts: { ACTIVE: 1 },
        active_value_by_currency: { RON: "250000.00" },
      } });
    }
    const items = [{
      id: "00000000-0000-0000-0000-000000000010",
      tenant_id: "00000000-0000-0000-0000-000000000002",
      contract_number: "CTR-001",
      title: "Servicii digitale",
      description: "Contract demonstrativ",
      value: "250000.00",
      currency: "RON",
      signed_date: "2026-09-20",
      start_date: "2026-10-01",
      end_date: "2027-09-30",
      status: "ACTIVE",
      responsible_department_id: null,
      responsible_user_id: null,
      created_by: "00000000-0000-0000-0000-000000000001",
      created_at: "2026-09-25T00:00:00Z",
      updated_at: "2026-09-25T00:00:00Z",
    }];
    if (route.request().url().includes("/contracts/page")) {
      return route.fulfill({ json: { items, total: 1, limit: 10, offset: 0 } });
    }
    return route.fulfill({ json: items });
  });
  await page.goto("/");
  await page.evaluate(() => window.localStorage.setItem("govcontrol.dev-token", "test-token"));
  await page.goto("/contracts");
  await expect(page.getByRole("heading", { name: "Controlul contractelor instituției" })).toBeVisible();
  await expect(page.getByText("250.000 RON", { exact: true })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Navigare GovContracts" })).toBeVisible();
  await page.getByRole("link", { name: "Registru contracte" }).click();
  await expect(page).toHaveURL(/\/contracts\/registry$/);
  await expect(page.getByRole("heading", { name: "Registrul contractelor" })).toBeVisible();
  await expect(page.getByText("CTR-001")).toBeVisible();
  expect(browserErrors).toEqual([]);
});
