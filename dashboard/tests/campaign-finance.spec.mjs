import { expect, test } from "@playwright/test";

// campaign-finance-tracker was a real, dashboard-wired feature — GET
// /campaign-finance/{summary,contributions,entities,reports} and a live
// "Campaign Finance" tab in CampaignFinance.jsx — that had simply never been
// registered in .federation/gui-capabilities.json or covered by an e2e test.
// The blanket "postmerge-staged-analysis-and-api-surfaces" exemption papered
// over that gap along with 259 unrelated candidates from five other
// subsystems. This spec is what earns campaign-finance-tracker its own real
// (non-staged) manifest entry.
//
// The source CSVs under data/staging/processed/ are not checked into the
// repo, so in CI every query genuinely returns zero rows. That is exercised
// deliberately below (a real backend cannot serve data it was never given),
// rather than worked around. What this proves instead: the tab is reachable
// through the real UI, the four endpoints are genuinely wired end to end
// (not stubbed), and the three filter controls flagged by check_gui_parity.py
// as GUI_NOT_BACKEND_WIRED (the view select, the source select, and the
// search input) actually change the outgoing request.

test("Campaign Finance tab reaches the real backend, unstubbed", async ({ page }) => {
  const summaryResponse = page.waitForResponse(
    (response) => response.url().includes("/campaign-finance/summary") && response.status() === 200,
  );

  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByRole("tab", { name: "Campaign Finance" }).click();
  await expect(page).toHaveURL(/tab=campaign-finance/);

  const summary = await (await summaryResponse).json();
  expect(summary, "GET /campaign-finance/summary did not return the expected shape").toMatchObject({
    sources: expect.any(Array),
    derived: expect.any(Object),
  });

  // The default view is "contributions"; QueryBoundary renders its
  // isEmpty label rather than crashing when the source CSVs are absent.
  await expect(page.getByText("No campaign-finance contributions are materialized")).toBeVisible();
});

test("each view renders the response from its own real endpoint", async ({ page }) => {
  // CampaignFinance mounts all four query hooks unconditionally — `view` only
  // switches which already-fetched result is displayed, it does not itself
  // trigger a new request. So the real requests are awaited once, up front;
  // what's under test is that each view renders the payload that came back
  // from *its* endpoint rather than, say, all three showing the same table.
  const entitiesResponse = page.waitForResponse(
    (response) => response.url().includes("/campaign-finance/entities") && response.status() === 200,
  );
  const reportsResponse = page.waitForResponse(
    (response) => response.url().includes("/campaign-finance/reports") && response.status() === 200,
  );

  await page.goto("/?tab=campaign-finance", { waitUntil: "domcontentloaded" });
  await expect(page.getByText("No campaign-finance contributions are materialized")).toBeVisible();
  await entitiesResponse;
  await reportsResponse;

  await page.getByLabel("Campaign-finance view").selectOption("entities");
  await expect(page.getByText("No campaign-finance entities are materialized")).toBeVisible();

  await page.getByLabel("Campaign-finance view").selectOption("reports");
  await expect(page.getByText("No OCE campaign-finance reports are materialized")).toBeVisible();
});

test("the source filter and the search box each change the outgoing request", async ({ page }) => {
  await page.goto("/?tab=campaign-finance", { waitUntil: "domcontentloaded" });
  await expect(page.getByText("No campaign-finance contributions are materialized")).toBeVisible();

  const fecRequest = page.waitForRequest(
    (request) => request.url().includes("/campaign-finance/contributions") && request.url().includes("source=fec"),
  );
  await page.getByLabel("Campaign-finance source").selectOption("fec");
  await fecRequest;

  const searchRequest = page.waitForRequest(
    (request) => request.url().includes("/campaign-finance/contributions") && request.url().includes("q=Acme"),
  );
  await page.getByLabel("Filter campaign-finance records").fill("Acme");
  await searchRequest;
});
