import { expect, test } from "@playwright/test";

const user = {
  id: "00000000-0000-0000-0000-000000000001",
  tenant_id: "00000000-0000-0000-0000-000000000002",
  department_id: null,
  email: "test@govcontrol.local",
  display_name: "Test User",
  roles: ["platform_admin"],
  permissions: ["legal.manage", "legal.report", "contracts.manage", "contracts.report"],
};

async function mockSession(page: import("@playwright/test").Page, authenticated = true) {
  await page.route("**/auth/config", (route) => route.fulfill({ json: { mode: "local", login_url: "/auth/login" } }));
  await page.route("**/auth/session", (route) => authenticated
    ? route.fulfill({ json: { user, csrf_token: "csrf-token", expires_at: "2026-09-26T00:00:00Z", auth_method: "local" } })
    : route.fulfill({ status: 401, json: { detail: "Authentication is required." } }));
}

test("shell-ul instituțional și conectarea sunt accesibile", async ({ page }) => {
  await mockSession(page, false);
  await page.goto("/legal");
  await expect(page.getByRole("heading", { name: "Panou de control juridic" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Navigare GovLegal" })).toBeVisible();
  await expect(page.getByRole("dialog", { name: "Conectează spațiul de lucru" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Conectează aplicația" })).toBeFocused();
});

test("navigarea deschide registrul de obligații", async ({ page }) => {
  await mockSession(page);
  await page.goto("/legal");
  await expect(page.getByRole("button", { name: /Test User/ })).toBeVisible();
  await page.getByRole("link", { name: "Obligații", exact: true }).click();
  await expect(page).toHaveURL(/\/legal\/obligations$/);
  await expect(page.getByRole("heading", { name: "Obligații instituționale" })).toBeVisible();
});

test("GovContracts afișează dashboard-ul și registrul din serviciul separat", async ({ page }) => {
  const browserErrors: string[] = [];
  page.on("pageerror", (error) => browserErrors.push(error.message));
  await mockSession(page);
  await page.route("**/api/v1/govcontracts/contracts**", (route) => {
    if (route.request().url().endsWith("/dashboard")) {
      return route.fulfill({ json: {
        total_contracts: 1,
        active_contracts: 1,
        expiring_within_30_days: 0,
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
