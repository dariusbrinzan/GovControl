import { expect, test } from "@playwright/test";

test("fluxul GovLegal real păstrează dashboardul, registrul și fișa dosarului", async ({ page }) => {
  const browserErrors: string[] = [];
  const failedApiCalls: string[] = [];
  page.on("pageerror", (error) => browserErrors.push(error.message));
  page.on("response", (response) => {
    if (response.url().includes("/api/v1/") && response.status() >= 400) {
      failedApiCalls.push(`${response.status()} ${response.url()}`);
    }
  });

  await page.goto("/legal");
  await page.getByRole("button", { name: "Conectează aplicația" }).click();
  await expect(page.getByRole("button", { name: /GovControl Development Admin/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Panou de control juridic" })).toBeVisible();
  await expect(page.getByText("Obligații active", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Evoluția obligațiilor" })).toBeVisible();

  await page.getByRole("link", { name: "Dosare", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Dosare juridice" })).toBeVisible();
  await expect(page.getByRole("link", { name: "GC-1452/3/2026" })).toBeVisible();
  await page.getByRole("link", { name: "GC-1452/3/2026" }).click();
  await expect(page.getByRole("heading", { name: "GC-1452/3/2026" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Hotărâri asociate" })).toBeVisible();

  await page.getByRole("button", { name: /GovControl Development Admin/ }).click();
  await page.getByRole("button", { name: "Deconectează" }).click();
  await expect(page.getByRole("dialog", { name: "Conectează spațiul de lucru" })).toBeVisible();

  expect(browserErrors).toEqual([]);
  expect(failedApiCalls).toEqual([]);
});

test("o sesiune revocată în gateway este respinsă de portalul real", async ({ page }) => {
  await page.goto("/legal");
  const loginResponsePromise = page.waitForResponse((response) =>
    response.url().endsWith("/auth/local/login"),
  );
  await page.getByRole("button", { name: "Conectează aplicația" }).click();
  const loginResponse = await loginResponsePromise;
  expect(loginResponse.status()).toBe(200);
  const { csrf_token: csrfToken } = (await loginResponse.json()) as { csrf_token: string };
  const gatewayOrigin = new URL(loginResponse.url()).origin;

  const logoutStatus = await page.evaluate(
    async ({ csrfToken, gatewayOrigin }) => {
      const response = await fetch(`${gatewayOrigin}/auth/logout`, {
        method: "POST",
        credentials: "include",
        headers: { "X-CSRF-Token": csrfToken },
      });
      return response.status;
    },
    { csrfToken, gatewayOrigin },
  );
  expect(logoutStatus).toBe(204);

  await page.reload();
  await expect(page.getByRole("dialog", { name: "Conectează spațiul de lucru" })).toBeVisible();
});
