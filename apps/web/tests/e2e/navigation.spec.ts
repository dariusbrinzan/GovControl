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
