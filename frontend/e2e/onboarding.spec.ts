import { expect, test } from "@playwright/test";
import path from "node:path";

const API = "http://localhost:8000";
const SAMPLE = path.join(__dirname, "..", "..", "samples", "customers.csv");

test("implementation specialist onboards a customer from setup to go-live", async ({ page, request }) => {
  const name = `Northwind ${Date.now()}`;

  // 1. Create workspace
  await page.goto("/");
  await page.getByLabel("Customer name").fill(name);
  await page.getByLabel("Customer contact email").fill("it@northwind.example");
  await page.getByLabel("Implementation specialist").fill("Jordan Implementer");
  await page.getByRole("button", { name: "Create workspace" }).click();
  await expect(page.getByRole("heading", { name })).toBeVisible();
  const wsUrl = page.url();

  // 2. Import CSV and map fields (suggestions pre-fill the mapping)
  await page.getByRole("link", { name: "Import & mapping" }).click();
  await page.getByTestId("csv-input").setInputFiles(SAMPLE);
  await expect(page.getByLabel("Map Tier")).toHaveValue("plan");
  await expect(page.getByLabel("Map Customer ID")).toHaveValue("external_id");
  await page.getByRole("button", { name: "Apply mapping & validate" }).click();
  await expect(page.getByRole("button", { name: "Commit 3 valid records" })).toBeVisible();

  // 3. Fix a failed record
  await page.getByRole("link", { name: "Failed records & errors" }).click();
  await expect(page.getByText("5 record(s) failed validation")).toBeVisible();
  await expect(page.getByText("Email is not a valid email address")).toBeVisible();
  await page.getByLabel("Row 4 email").fill("dmitri@northwind.example");
  await page.getByLabel("Row 4 email").locator("xpath=ancestor::tr").getByRole("button", { name: "Save & revalidate" }).click();
  await expect(page.getByText("4 record(s) failed validation")).toBeVisible();

  // 4. Commit valid records
  await page.getByRole("link", { name: "Import & mapping" }).click();
  await page.getByRole("button", { name: "Commit 4 valid records" }).click();
  await expect(page.getByText("4 records loaded into the platform")).toBeVisible();

  // 5. Credentials and webhooks (one healthy, one failing receiver)
  await page.getByRole("link", { name: "Credentials & webhooks" }).click();
  await page.getByLabel("Key name").fill("Production sync");
  await page.getByLabel("Environment").selectOption("production");
  await page.getByRole("button", { name: "Generate key" }).click();
  const apiKey = (await page.getByTestId("new-api-key").textContent())!.trim();
  expect(apiKey).toMatch(/^oc_live_/);

  for (const outcome of ["ok", "fail"]) {
    await page.getByLabel("Endpoint URL").fill(`${API}/sink/${outcome}`);
    await page.getByRole("button", { name: "Add endpoint" }).click();
    await expect(page.getByText(`${API}/sink/${outcome}`, { exact: true })).toBeVisible();
  }

  // 6. Tests fail because of the broken webhook…
  await page.getByRole("link", { name: "Validation & tests" }).click();
  await page.getByRole("button", { name: "Run tests" }).click();
  await expect(page.getByTestId("test-result")).toContainText("Failed");
  await expect(page.getByText("Endpoint responded with HTTP 500").first()).toBeVisible();

  // …which shows up in the webhook error view
  await page.getByRole("link", { name: "Failed records & errors" }).click();
  await expect(page.getByRole("heading", { name: "Webhook errors" })).toBeVisible();
  await expect(page.getByRole("cell", { name: `${API}/sink/fail` }).first()).toBeVisible();

  // 7. Pause the broken endpoint and re-run
  await page.getByRole("link", { name: "Credentials & webhooks" }).click();
  await page
    .locator(".card .card", { hasText: `${API}/sink/fail` })
    .getByRole("button", { name: "Pause" })
    .click();
  await page.getByRole("link", { name: "Validation & tests" }).click();
  await page.getByRole("button", { name: "Run tests" }).click();
  await expect(page.getByTestId("test-result")).toContainText("Passed");

  // 8. UAT checklist
  await page.getByRole("link", { name: "UAT checklist" }).click();
  await page.getByLabel("Signing off as").fill("Pat Customer");
  const boxes = page.locator('table input[type="checkbox"]');
  const count = await boxes.count();
  for (let i = 0; i < count; i++) {
    await boxes.nth(i).click(); // controlled input: state flips after the API round-trip
    await expect(boxes.nth(i)).toBeChecked();
  }
  await expect(page.getByText(`${count} of ${count} complete`)).toBeVisible();

  // 9. Go live
  await page.goto(wsUrl);
  await expect(page.getByText("All gates passed")).toBeVisible();
  await page.getByRole("button", { name: "Go live" }).click();
  await expect(page.locator(".banner-good", { hasText: "Live since" })).toBeVisible();

  // 10. Handover document
  await page.getByRole("link", { name: "Handover document" }).click();
  const doc = page.getByTestId("handover");
  await expect(doc).toContainText(`Customer Handover — ${name}`);
  await expect(doc).toContainText("LIVE");
  await expect(doc).toContainText("UAT sign-off (8/8)");
  await expect(doc).not.toContainText(apiKey);

  // 11. Post-launch traffic via the customer API, then monitoring
  const res = await request.post(`${API}/api/v1/records`, {
    headers: { Authorization: `Bearer ${apiKey}` },
    data: { records: [{ external_id: "NW-2000", email: "new@northwind.example", plan: "pro" }, { email: "bad" }] },
  });
  expect(res.status()).toBe(200);
  expect((await res.json()).accepted).toBe(1);

  await page.getByRole("link", { name: "Monitoring" }).click();
  await expect(page.getByRole("heading", { name: /Integration health/ })).toBeVisible();
  await expect(page.locator(".stat", { hasText: "API requests" }).locator(".stat-value")).toHaveText("1");
  await expect(page.locator(".stat", { hasText: "Customer records" }).locator(".stat-value")).toHaveText("5");
});
