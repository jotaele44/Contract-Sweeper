import { expect, test } from "@playwright/test";

// api-key-management: the "API Keys" tab (ApiKeysPanel.jsx) and its backend
// (server/backend/api_keys.py, GET/POST /api-keys). Verifies the tab is
// reachable through the real UI, GET /api-keys is genuinely wired (not
// stubbed — real entries parsed from .env.example), and that saving a
// value round-trips through a real POST without ever echoing the value back
// in any response body, matching docs/SECRET_HANDLING_POLICY.md.

test("API Keys tab reaches the real backend and lists all known keys", async ({ page }) => {
  const listResponse = page.waitForResponse(
    (response) => response.url().includes("/api-keys") && response.request().method() === "GET" && response.status() === 200,
  );

  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByRole("tab", { name: "API Keys" }).click();
  await expect(page).toHaveURL(/tab=api-keys/);
  await expect(page.getByTestId("api-keys-panel")).toBeVisible();

  const rows = await (await listResponse).json();
  expect(rows.length, "GET /api-keys returned an empty registry").toBeGreaterThan(0);
  expect(new Set(rows.map((row) => row.name)).size, "GET /api-keys returned duplicate names").toBe(rows.length);
  for (const row of rows) {
    expect(Object.keys(row).sort()).toEqual(["description", "is_set", "name", "required"]);
    await expect(page.getByTestId(`api-key-row-${row.name}`)).toBeVisible();
  }
});

test("saving a key does a real POST and never echoes the value back", async ({ page }) => {
  const secret = "e2e-fixture-value-not-a-real-credential";

  await page.goto("/?tab=api-keys", { waitUntil: "domcontentloaded" });
  const row = page.getByTestId("api-key-row-CENSUS_API_KEY");
  await expect(row).toBeVisible();

  const postResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/api-keys/CENSUS_API_KEY") &&
      response.request().method() === "POST",
  );

  await row.locator('input[type="password"]').fill(secret);
  await row.getByRole("button", { name: "Save" }).click();

  const response = await postResponse;
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(body).toEqual({ name: "CENSUS_API_KEY", is_set: true });
  expect(JSON.stringify(body)).not.toContain(secret);

  await expect(page.getByTestId("api-key-status-CENSUS_API_KEY")).toHaveText("Set");
  // The input clears after a successful save — the value is never left
  // sitting in the DOM once it's been submitted.
  await expect(row.locator('input[type="password"]')).toHaveValue("");
});
