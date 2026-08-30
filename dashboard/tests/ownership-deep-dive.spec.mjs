import { expect, test } from "@playwright/test";

// The authoritative SEC data snapshot is intentionally not committed to the
// repository. CI therefore exercises the real terminal-free promotion boundary:
// the status endpoint is reachable, provider equivalence remains OPEN, the BPOP
// surface is discoverable, and absence of the independently certified artifacts
// fails closed rather than substituting fixture/provider data.
test("Ownership tab reaches the real certified-scope backend boundary", async ({ page }) => {
  const statusResponse = page.waitForResponse(
    (response) => response.url().includes("/deep-dive/ownership/status") && response.status() === 200,
  );
  const bpopResponse = page.waitForResponse(
    (response) => response.url().includes("/deep-dive/ownership/BPOP"),
  );

  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByRole("tab", { name: "Ownership" }).click();
  await expect(page).toHaveURL(/tab=ownership/);

  const status = await (await statusResponse).json();
  expect(status).toMatchObject({
    certifiedIssuer: "BPOP",
    providerEquivalence: "OPEN",
  });

  const bpop = await bpopResponse;
  expect([200, 503]).toContain(bpop.status());
  await expect(page.getByText(/Provider equivalence:/)).toContainText("OPEN");
  await expect(page.getByLabel("Ownership issuer")).toHaveValue("BPOP");

  if (bpop.status() === 503) {
    await expect(page.getByText("Couldn’t reach the backend")).toBeVisible();
  } else {
    await expect(page.getByText("Certification scope")).toBeVisible();
  }
});

test("OFG and EVTC are discoverable only as disabled regression controls", async ({ page }) => {
  await page.goto("/?tab=ownership", { waitUntil: "domcontentloaded" });
  const selector = page.getByLabel("Ownership issuer");
  await expect(selector.locator('option[value="OFG"]')).toBeDisabled();
  await expect(selector.locator('option[value="EVTC"]')).toBeDisabled();
  await expect(selector.locator('option[value="BPOP"]')).toBeEnabled();
});
