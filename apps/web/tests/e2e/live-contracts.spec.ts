import { expect, test } from "@playwright/test";

const token = process.env.DEV_AUTH_TOKEN;

test("fluxul GovContracts real afișează datele agregate și fișa completă", async ({ page }) => {
  test.skip(!token, "DEV_AUTH_TOKEN is required for the live local integration test.");
  const browserErrors: string[] = [];
  const failedApiCalls: string[] = [];
  page.on("pageerror", (error) => browserErrors.push(error.message));
  page.on("response", (response) => {
    if (response.url().includes("/api/v1/") && response.status() >= 400) {
      failedApiCalls.push(`${response.status()} ${response.url()}`);
    }
  });
  await page.goto("/");
  await page.evaluate((value) => window.localStorage.setItem("govcontrol.dev-token", value), token!);
  await page.goto("/contracts");
  await expect(page.getByRole("heading", { name: "Controlul contractelor instituției" })).toBeVisible();
  await expect(page.getByText("Contracte active", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Registru contracte" }).click();
  await expect(page.getByText("CTR-DEMO-001")).toBeVisible();
  await page.getByRole("link", { name: "CTR-DEMO-001" }).click();
  await expect(page.getByRole("heading", { name: "CTR-DEMO-001" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Părți contractuale" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Acte adiționale" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Jaloane și termene" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Obligații contractuale" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Plăți planificate" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Documente asociate" })).toBeVisible();
  await expect(page.locator('select[aria-label^="Actualizează statusul"]').first()).toBeVisible();
  await expect(page.getByText("Departament responsabil", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Editează contract" }).click();
  await expect(page.getByLabel("Departament responsabil")).toHaveValue(/.*/);
  await expect(page.getByLabel("Departament responsabil").locator("option")).not.toHaveCount(1);
  await page.getByRole("button", { name: "Renunță" }).click();
  await page.getByRole("link", { name: "Jurnal de audit" }).click();
  await expect(page.getByRole("heading", { name: "Jurnal audit GovContracts" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Request ID" })).toBeVisible();
  expect(browserErrors).toEqual([]);
  expect(failedApiCalls).toEqual([]);
});
