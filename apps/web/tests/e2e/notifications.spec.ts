import { expect, test } from "@playwright/test";

const user = {
  id: "00000000-0000-0000-0000-000000000001",
  tenant_id: "00000000-0000-0000-0000-000000000002",
  department_id: null,
  email: "test@govcontrol.local",
  display_name: "Test User",
  roles: ["platform_admin"],
  permissions: [
    "notifications.read",
    "notifications.manage",
    "notifications.preferences",
  ],
};

const notification = {
  id: "00000000-0000-4000-8000-000000000010",
  category: "LEGAL",
  severity: "WARNING",
  title: "Termen juridic apropiat",
  body: "Resursa juridică necesită atenție.",
  resource_type: "LegalObligation",
  resource_id: "00000000-0000-4000-8000-000000000011",
  resource_url: "/legal/obligations/00000000-0000-4000-8000-000000000011",
  status: "UNREAD",
  read_at: null,
  archived_at: null,
  created_at: "2026-09-26T09:00:00Z",
};

test("centrul unificat gestionează inboxul, badge-ul și preferințele", async ({ page }) => {
  let current = {
    ...notification,
    status: "UNREAD" as string,
    read_at: null as string | null,
  };
  let preferenceEnabled = true;
  await page.route("**/auth/config", (route) =>
    route.fulfill({ json: { mode: "local", login_url: "/auth/login" } }),
  );
  await page.route("**/auth/session", (route) =>
    route.fulfill({
      json: {
        user,
        csrf_token: "csrf-token",
        expires_at: "2026-09-27T00:00:00Z",
        auth_method: "local",
      },
    }),
  );
  await page.route("**/api/v1/notifications**", async (route) => {
    const url = new URL(route.request().url());
    const method = route.request().method();
    if (url.pathname.endsWith("/unread-count")) {
      return route.fulfill({ json: { count: current.status === "UNREAD" ? 1 : 0 } });
    }
    if (url.pathname.endsWith("/preferences")) {
      if (method === "PUT") {
        const input = route.request().postDataJSON() as { enabled: boolean };
        preferenceEnabled = input.enabled;
      }
      const preference = {
          id: "00000000-0000-4000-8000-000000000012",
          category: "LEGAL",
          channel: "IN_APP",
          enabled: preferenceEnabled,
          quiet_hours_start: null,
          quiet_hours_end: null,
          updated_at: "2026-09-26T09:00:00Z",
      };
      return route.fulfill({ json: method === "GET" ? [preference] : preference });
    }
    if (url.pathname.endsWith("/mark-all-read")) {
      current = { ...current, status: "READ", read_at: "2026-09-26T10:00:00Z" };
      return route.fulfill({ json: { updated: 1 } });
    }
    const action = url.pathname.split("/").at(-1);
    if (method === "PATCH") {
      if (action === "archive") current = { ...current, status: "ARCHIVED" };
      if (action === "restore" || action === "unread") current = { ...current, status: "UNREAD" };
      if (action === "read") current = { ...current, status: "READ" };
      return route.fulfill({ json: current });
    }
    return route.fulfill({
      json: { items: [current], total: 1, limit: 20, offset: 0 },
    });
  });

  await page.goto("/legal/notifications");
  await expect(page.getByRole("heading", { name: "Centrul de notificări" })).toBeVisible();
  await expect(page.getByText("Termen juridic apropiat")).toBeVisible();
  await expect(page.getByRole("button", { name: "Notificări necitite: 1" })).toBeVisible();

  await page.getByRole("button", { name: "Marchează citită", exact: true }).click();
  await expect(page.getByRole("button", { name: "Marchează necitită" })).toBeVisible();
  await page.getByRole("button", { name: "Arhivează" }).click();
  await expect(page.getByRole("button", { name: "Restaurează" })).toBeVisible();
  await page.getByRole("button", { name: "Restaurează" }).click();
  await page.getByRole("button", { name: "Marchează toate citite" }).click();
  await expect(page.getByText("1 notificări au fost marcate ca citite.")).toBeVisible();

  const legalPreference = page.getByText("LEGAL", { exact: true }).last().locator("..").getByRole("checkbox");
  await legalPreference.click();
  await expect.poll(() => preferenceEnabled).toBe(false);
});

test("lipsa permisiunii de citire produce o stare forbidden explicită", async ({ page }) => {
  await page.route("**/auth/config", (route) => route.fulfill({ json: { mode: "local" } }));
  await page.route("**/auth/session", (route) =>
    route.fulfill({
      json: {
        user: { ...user, permissions: [] },
        csrf_token: "csrf-token",
        expires_at: "2026-09-27T00:00:00Z",
        auth_method: "local",
      },
    }),
  );
  await page.goto("/legal/notifications");
  await expect(page.getByText("Rolul curent nu are permisiunea notifications.read.")).toBeVisible();
});
