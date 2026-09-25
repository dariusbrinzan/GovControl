import { expect, test } from "@playwright/test";

const token = process.env.DEV_AUTH_TOKEN;

test("fluxul GovLegal real păstrează dashboardul, registrul și fișa dosarului", async ({ page }) => {
  test.skip(!token, "DEV_AUTH_TOKEN is required for the live local integration test.");
  const browserErrors: string[] = [];
  const failedApiCalls: string[] = [];
  page.on("pageerror", (error) => browserErrors.push(error.message));
  page.on("response", (response) => {
    if (new URL(response.url()).port === "8000" && response.status() >= 400) {
      failedApiCalls.push(`${response.status()} ${response.url()}`);
    }
  });

  await page.goto("/");
  await page.evaluate((value) => window.localStorage.setItem("govcontrol.dev-token", value), token!);
  await page.goto("/legal");
  await expect(page.getByRole("heading", { name: "Panou de control juridic" })).toBeVisible();
  await expect(page.getByText("Obligații active", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Evoluția obligațiilor" })).toBeVisible();

  await page.getByRole("link", { name: "Dosare", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Dosare juridice" })).toBeVisible();
  await expect(page.getByRole("link", { name: "GC-1452/3/2026" })).toBeVisible();
  await page.getByRole("link", { name: "GC-1452/3/2026" }).click();
  await expect(page.getByRole("heading", { name: "GC-1452/3/2026" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Hotărâri asociate" })).toBeVisible();

  expect(browserErrors).toEqual([]);
  expect(failedApiCalls).toEqual([]);
});
