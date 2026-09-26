import { expect, test } from "@playwright/test";
import { writeFile } from "node:fs/promises";

type NotificationPage = {
  items: Array<{ id: string; resource_id: string | null; status: string; category: string }>;
};

test("GovNotifications procesează evenimente Contract/Documents și inboxul prin Gateway", async ({ page, request }) => {
  const startedAt = new Date().toISOString();
  const origin = "http://localhost:8080";
  const login = await request.post(`${origin}/auth/local/login`, {
    headers: { Origin: "http://localhost:3000" },
  });
  expect(login.status()).toBe(200);
  const { csrf_token: csrf } = (await login.json()) as { csrf_token: string };
  const storage = await request.storageState();
  expect(storage.cookies.some((cookie) => cookie.name === "govcontrol_session")).toBe(true);
  await page.context().addCookies(storage.cookies);
  await page.goto("/legal");
  await expect(
    page.getByRole("button", { name: /GovControl Development Admin/ }),
  ).toBeVisible();

  const contractsResponse = await request.get(
    `${origin}/api/v1/govcontracts/contracts?limit=1`,
  );
  expect(contractsResponse.status()).toBe(200);
  const contracts = (await contractsResponse.json()) as Array<{ id: string; title: string }>;
  const contract = contracts[0];
  expect(contract).toBeTruthy();
  const markerTitle = `${contract.title} [notification-e2e]`;
  expect((await request.patch(
    `${origin}/api/v1/govcontracts/contracts/${contract.id}`,
    { headers: { "X-CSRF-Token": csrf }, data: { title: markerTitle } },
  )).status()).toBe(200);
  expect((await request.patch(
    `${origin}/api/v1/govcontracts/contracts/${contract.id}`,
    { headers: { "X-CSRF-Token": csrf }, data: { title: contract.title } },
  )).status()).toBe(200);

  const casesResponse = await request.get(`${origin}/api/v1/platform/legal/cases`);
  expect(casesResponse.status()).toBe(200);
  const cases = (await casesResponse.json()) as Array<{ id: string }>;
  const caseId = cases[0]?.id;
  expect(caseId).toBeTruthy();
  const documentResponse = await request.post(`${origin}/api/v1/documents`, {
    headers: { "X-CSRF-Token": csrf },
    multipart: {
      resource_type: "LegalCase",
      resource_id: caseId,
      category: "E2E",
      file: {
        name: `e2e-notification-${Date.now()}.txt`,
        mimeType: "text/plain",
        buffer: Buffer.from("GovNotifications live event"),
      },
    },
  });
  expect(documentResponse.status()).toBe(201);
  const documentId = ((await documentResponse.json()) as { id: string }).id;
  await writeFile(
    "/tmp/govcontrol-notifications-e2e.json",
    JSON.stringify({
      started_at: startedAt,
      resource_ids: [contract.id, documentId],
      contract_ids: [contract.id],
    }),
  );

  await expect.poll(async () => {
    const response = await request.get(
      `${origin}/api/v1/notifications?limit=100&offset=0`,
    );
    if (!response.ok()) return { contract: false, document: false };
    const result = (await response.json()) as NotificationPage;
    return {
      contract: result.items.some((item) => item.resource_id === contract.id),
      document: result.items.some((item) => item.resource_id === documentId),
    };
  }, { timeout: 30_000 }).toEqual({ contract: true, document: true });

  const normalList = await request.get(`${origin}/api/v1/notifications?limit=100`);
  const forgedList = await request.get(`${origin}/api/v1/notifications?limit=100`, {
    headers: {
      "X-Tenant-ID": "00000000-0000-0000-0000-000000000099",
    },
  });
  expect(await forgedList.json()).toEqual(await normalList.json());
  const foreignMutation = await request.patch(
    `${origin}/api/v1/notifications/00000000-0000-4000-8000-000000000099/read`,
    { headers: { "X-CSRF-Token": csrf } },
  );
  expect(foreignMutation.status()).toBe(404);

  await page.goto("/legal/notifications");
  await expect(page.getByRole("heading", { name: "Centrul de notificări" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Notificări necitite:/ })).toBeVisible();
  const contractCard = page.locator("article").filter({ hasText: contract.id }).first();
  await expect(contractCard).toBeVisible();
  await contractCard.getByRole("button", { name: "Marchează citită" }).click();
  await expect(contractCard.getByRole("button", { name: "Marchează necitită" })).toBeVisible();
  await contractCard.getByRole("button", { name: "Arhivează" }).click();
  await expect(contractCard.getByRole("button", { name: "Restaurează" })).toBeVisible();
  await contractCard.getByRole("button", { name: "Restaurează" }).click();
  await page.getByRole("button", { name: "Marchează toate citite" }).click();
  await expect(page.getByRole("status")).toContainText("marcate ca citite");

  expect((await request.post(`${origin}/auth/logout`, {
    headers: { "X-CSRF-Token": csrf },
  })).status()).toBe(204);
  expect((await request.get(`${origin}/auth/session`)).status()).toBe(401);
  await page.reload();
  await expect(page.getByRole("button", { name: "Conectează aplicația" })).toBeVisible();
});
