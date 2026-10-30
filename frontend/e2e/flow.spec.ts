import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Officer credentials come from the same env file the server was seeded from (never hardcoded).
function env(name: string): string {
  if (process.env[name]) return process.env[name] as string;
  const file = path.resolve(__dirname, "../../.env");
  const line = fs.existsSync(file) ? fs.readFileSync(file, "utf8").split(/\r?\n/).find((l) => l.startsWith(`${name}=`)) : undefined;
  const v = line?.slice(name.length + 1).split(/\s+#/)[0].trim();
  if (!v) throw new Error(`${name} is not set`);
  return v;
}

const fixtures = path.resolve(__dirname, "fixtures");
const stamp = Date.now();
const worker = { email: `e2e.worker.${stamp}@example.com`, password: `Flowpass${stamp % 100000}9`, name: "Kumar Velu" };

async function login(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

async function logout(page: Page) {
  await page.getByRole("button", { name: "Sign out" }).first().click();
  await expect(page).toHaveURL(/\/login/);
}

test("worker uploads -> score -> shares -> officer reviews and decides -> worker sees decision", async ({ page }) => {
  // 1. register
  await page.goto("/register");
  await page.getByLabel("Full name").fill(worker.name);
  await page.getByLabel("Email").fill(worker.email);
  await page.getByLabel("Password").fill(worker.password);
  await page.getByLabel("City").selectOption("Chennai");
  await page.getByLabel("Type of work").selectOption("rider");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Consents", level: 1 })).toBeVisible();

  // 2. per-source consent, then upload a bank statement and two payout statements
  await page.goto("/worker/sources");
  await page.getByRole("button", { name: /Give consent/ }).click();
  await page.getByLabel("File").setInputFiles(path.join(fixtures, "bank_statement.csv"));
  await page.getByRole("button", { name: "Upload and read" }).click();
  await expect(page.getByText(/Statement read: \d+ rows added/)).toBeVisible();

  for (const [file, platform] of [["swiggy_payouts.csv", "Swiggy"], ["rapido_payouts.csv", "Rapido"]]) {
    await page.getByLabel("Platform payout statement").check();
    const give = page.getByRole("button", { name: /Give consent/ });
    if (await give.isVisible()) await give.click();
    await page.getByLabel("Platform", { exact: true }).selectOption(platform);
    await page.getByLabel("File").setInputFiles(path.join(fixtures, file));
    await page.getByRole("button", { name: "Upload and read" }).click();
    await expect(page.getByText(/Statement read: \d+ rows added/)).toBeVisible();
    await expect(page.getByText(file, { exact: false }).first()).toBeVisible();
  }
  await expect(page.getByText("Ready")).toHaveCount(3);

  // 3. passport with a computed score, reconciled payouts and evidence drill-down
  await page.getByRole("link", { name: "My Passport" }).click();
  await expect(page.getByRole("heading", { name: "My Earnings Passport" })).toBeVisible();
  await expect(page.getByText("Payouts matched to bank credits")).toBeVisible();
  const score = await page.locator("section[aria-label='EarnScore'] .text-3xl").innerText();
  expect(Number(score)).toBeGreaterThanOrEqual(0);
  await page.getByRole("button", { name: /^Consistency/ }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByRole("dialog").locator("tbody tr").first()).toBeVisible();
  await page.getByRole("button", { name: "Close" }).click();

  // language switch reaches worker pages
  await page.getByLabel("Language").selectOption("ta");
  await expect(page.getByRole("heading", { name: "என் வருமான பாஸ்போர்ட்" })).toBeVisible();
  await page.getByLabel("மொழி").selectOption("en");

  // 4. share with a lender
  await page.getByRole("link", { name: "Share" }).click();
  await page.getByLabel("Lender").selectOption({ label: "Nilavu Community Credit" });
  await page.getByLabel("Loan amount (₹)").fill("20000");
  await page.getByRole("button", { name: "Share my passport" }).click();
  await expect(page.getByText("Nilavu Community Credit").last()).toBeVisible();
  await logout(page);

  // 5. officer reviews the report, opens evidence, decides with a reason code
  await login(page, env("SEED_OFFICER_EMAIL"), env("SEED_OFFICER_PASSWORD"));
  await expect(page.getByRole("heading", { name: "Applications" })).toBeVisible();
  await page.getByRole("link", { name: worker.name }).first().click();
  await expect(page.getByText("Suggested loan shape")).toBeVisible();
  await page.getByRole("button", { name: /^Capacity/ }).click();
  await expect(page.getByRole("dialog").locator("tbody tr").first()).toBeVisible();
  await page.getByRole("button", { name: "Close" }).click();
  await page.getByRole("button", { name: /Payouts matched to bank/ }).click();
  await expect(page.getByRole("dialog").getByText("Matched payout")).toBeVisible();
  await page.getByRole("button", { name: "Close" }).click();

  await page.getByLabel("Modify").check();
  await page.getByRole("button", { name: "Record decision" }).click();
  await expect(page.getByText("Choose a reason code.")).toBeVisible(); // reason code is mandatory
  await page.getByLabel("Reason code").selectOption("ADD_SKIP_WEEK");
  await page.getByLabel("Note").fill("Weekly EMI on payout day with the seasonal skip-week.");
  await page.getByRole("button", { name: "Record decision" }).click();
  await expect(page.getByText("Decision record")).toBeVisible();
  await logout(page);

  // 6. worker sees the decision
  await login(page, worker.email, worker.password);
  await page.getByRole("link", { name: "Share" }).click();
  await expect(page.getByText("Lender's decision: Approved with changes")).toBeVisible();
  await expect(page.getByText("add skip week")).toBeVisible();
});
