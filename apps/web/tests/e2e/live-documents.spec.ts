import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";

test("GovDocuments gestionează upload, download, versiuni, audit și restaurare prin Gateway", async ({ page }) => {
  const filename = `e2e-dosar-${Date.now()}.txt`;
  await page.goto("/legal");
  await page.getByRole("button", { name: "Conectează aplicația" }).click();
  await page.getByRole("link", { name: "Dosare", exact: true }).click();
  await page.getByRole("link", { name: "GC-1452/3/2026" }).click();

  await page.getByLabel("Adaugă document").setInputFiles({
    name: filename,
    mimeType: "text/plain",
    buffer: Buffer.from("prima versiune GovDocuments E2E"),
  });
  await page.getByRole("button", { name: "Încarcă", exact: true }).click();
  await expect(page.getByRole("link", { name: filename })).toBeVisible();
  await page.getByRole("link", { name: filename }).click();
  await expect(page.getByRole("heading", { name: "Versiuni" })).toBeVisible();
  await expect(page.getByText("v1", { exact: false }).first()).toBeVisible();

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Descarcă versiunea" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe(filename);
  const downloadedPath = await download.path();
  expect(downloadedPath).not.toBeNull();
  expect(await readFile(downloadedPath!, "utf8")).toBe("prima versiune GovDocuments E2E");

  await page.getByLabel("Versiune nouă").setInputFiles({
    name: filename,
    mimeType: "text/plain",
    buffer: Buffer.from("a doua versiune GovDocuments E2E"),
  });
  await page.getByRole("button", { name: "Încarcă versiune" }).click();
  await expect(page.getByText("v2", { exact: false }).first()).toBeVisible();
  await expect(page.getByText("document.version created", { exact: false })).toBeVisible();

  await page.getByRole("button", { name: "Șterge" }).click();
  await expect(page.getByRole("button", { name: "Restaurează" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("button", { name: "Restaurează" })).toBeVisible();
  await page.getByRole("button", { name: "Restaurează" }).click();
  await expect(page.getByRole("button", { name: "Șterge" })).toBeVisible();
  await page.getByRole("button", { name: "Șterge" }).click();
  await expect(page.getByRole("button", { name: "Restaurează" })).toBeVisible();
});

test("Gateway blochează mutațiile fără CSRF și ignoră tenantul furnizat de client", async ({ page }) => {
  await page.goto("/legal");
  const loginResponsePromise = page.waitForResponse((response) =>
    response.url().endsWith("/auth/local/login"),
  );
  await page.getByRole("button", { name: "Conectează aplicația" }).click();
  const loginResponse = await loginResponsePromise;
  expect(loginResponse.status()).toBe(200);
  const { csrf_token: csrfToken } = (await loginResponse.json()) as { csrf_token: string };
  const gatewayOrigin = new URL(loginResponse.url()).origin;

  const listResponse = await page.request.get(`${gatewayOrigin}/api/v1/documents?page_size=1`, {
    headers: { "X-Tenant-ID": "00000000-0000-0000-0000-000000000099" },
  });
  expect(listResponse.status()).toBe(200);
  const listed = (await listResponse.json()) as { items: Array<{ tenant_id: string }> };
  expect(listed.items[0]?.tenant_id).not.toBe("00000000-0000-0000-0000-000000000099");

  const forbidden = await page.request.post(`${gatewayOrigin}/api/v1/documents`, {
    multipart: {
      resource_type: "LegalCase",
      resource_id: "00000000-0000-0000-0000-000000000099",
      category: "E2E",
      file: { name: "forbidden.txt", mimeType: "text/plain", buffer: Buffer.from("blocked") },
    },
  });
  expect(forbidden.status()).toBe(403);

  const unavailableResource = await page.request.post(`${gatewayOrigin}/api/v1/documents`, {
    headers: { "X-CSRF-Token": csrfToken },
    multipart: {
      resource_type: "LegalCase",
      resource_id: "00000000-0000-0000-0000-000000000099",
      category: "E2E",
      file: { name: "unknown-resource.txt", mimeType: "text/plain", buffer: Buffer.from("blocked") },
    },
  });
  expect(unavailableResource.status()).toBe(404);
});

test("GovContracts atașează un document prin GovDocuments", async ({ page }) => {
  const filename = `e2e-contract-${Date.now()}.txt`;
  await page.goto("/contracts");
  await page.getByRole("button", { name: "Conectează aplicația" }).click();
  await page.getByRole("link", { name: "Registru contracte" }).click();
  await page.getByRole("link", { name: "CTR-DEMO-001" }).click();
  await page.getByLabel("Adaugă document").setInputFiles({
    name: filename,
    mimeType: "text/plain",
    buffer: Buffer.from("document contractual GovDocuments E2E"),
  });
  await page.getByRole("button", { name: "Încarcă", exact: true }).click();
  await expect(page.getByText(filename, { exact: true })).toBeVisible();
  await page.getByRole("link", { name: `Gestionează ${filename}` }).click();
  await page.getByRole("button", { name: "Șterge" }).click();
  await expect(page.getByRole("button", { name: "Restaurează" })).toBeVisible();
});
