import { expect, test } from "@playwright/test";

test("fluxul GovContracts real afișează datele agregate și fișa completă", async ({ page }) => {
  const browserErrors: string[] = [];
  const failedApiCalls: string[] = [];
  page.on("pageerror", (error) => browserErrors.push(error.message));
  page.on("response", (response) => {
    if (response.url().includes("/api/v1/") && response.status() >= 400) {
      failedApiCalls.push(`${response.status()} ${response.url()}`);
    }
  });
  await page.goto("/contracts");
  await page.getByRole("button", { name: "Conectează aplicația" }).click();
  await expect(page.getByRole("button", { name: /GovControl Development Admin/ })).toBeVisible();
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
  const originalTitle = await page.getByLabel("Titlu").inputValue();
  const changedTitle = `${originalTitle} [E2E]`;
  await page.getByLabel("Titlu").fill(changedTitle);
  await page.getByRole("button", { name: "Salvează modificările" }).click();
  await expect(page.getByText(changedTitle, { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Editează contract" }).click();
  await page.getByLabel("Titlu").fill(originalTitle);
  await page.getByRole("button", { name: "Salvează modificările" }).click();
  await expect(page.getByText(originalTitle, { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Jurnal de audit" }).click();
  await expect(page.getByRole("heading", { name: "Jurnal audit GovContracts" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Request ID" })).toBeVisible();
  expect(browserErrors).toEqual([]);
  expect(failedApiCalls).toEqual([]);
});
