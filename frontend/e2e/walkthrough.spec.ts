// Follows the manual test walkthrough step by step (sections A–E) and checks what each step should show.
// Run against a freshly started container: it records decisions, revokes consents and resolves nothing it did not create.
import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

function env(name: string): string {
  if (process.env[name]) return process.env[name] as string;
  const file = path.resolve(__dirname, "../../.env");
  const line = fs.existsSync(file) ? fs.readFileSync(file, "utf8").split(/\r?\n/).find((l) => l.startsWith(`${name}=`)) : undefined;
  const v = line?.slice(name.length + 1).split(/\s+#/)[0].trim();
  if (!v) throw new Error(`${name} is not set`);
  return v;
}

const fixtures = path.resolve(__dirname, "fixtures");
const stamp = Date.now() % 100000;
const me = { name: `Kumar Velu ${stamp}`, email: `kumar.velu.${stamp}@example.com`, password: `Velu${stamp}pass1` };
const officer = () => ({ email: env("SEED_OFFICER_EMAIL"), password: env("SEED_OFFICER_PASSWORD") });
const admin = () => ({ email: env("SEED_ADMIN_EMAIL"), password: env("SEED_ADMIN_PASSWORD") });
const workerPw = () => env("SEED_WORKER_PASSWORD");

async function login(page: Page, email: string, password: string) {
  // this script signs in more than 10 times a minute; wait out the rate limit like a person would
  for (let attempt = 0; attempt < 3; attempt++) {
    await page.goto("/login");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(password);
    const res = page.waitForResponse((r) => r.url().endsWith("/api/auth/login"));
    await page.getByRole("button", { name: "Sign in" }).click();
    if ((await res).status() !== 429) break;
    await page.waitForTimeout(61_000);
  }
  await expect(page).not.toHaveURL(/\/login/);
}

async function logout(page: Page) {
  await page.getByRole("button", { name: /Sign out|வெளியேறு|साइन आउट/ }).first().click();
  await expect(page).toHaveURL(/\/login/);
}

async function upload(page: Page, file: string, platform?: string) {
  if (platform) {
    await page.getByLabel("Platform payout statement").check();
    await page.getByLabel("Platform", { exact: true }).selectOption(platform);
  } else {
    await page.getByLabel("Bank statement", { exact: true }).check();
  }
  await page.getByLabel("File").setInputFiles(path.join(fixtures, file));
  await page.getByRole("button", { name: "Upload and read" }).click();
}

test.describe.configure({ mode: "serial", timeout: 300_000 });

test("A. worker path", async ({ page }) => {
  // A1 register
  await page.goto("/register");
  await page.getByLabel("Full name").fill(me.name);
  await page.getByLabel("Email").fill(me.email);
  await page.getByLabel("Password").fill(me.password);
  await page.getByLabel("City").selectOption("Chennai");
  await page.getByLabel("Type of work").selectOption("rider");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Consents", level: 1 })).toBeVisible();
  await expect(page.getByText("No consents yet.")).toBeVisible();

  // A2 one consent per source type
  await page.getByLabel("What we may read").selectOption("bank_statement");
  await page.getByRole("button", { name: "Give consent" }).click();
  await expect(page.getByText("Bank statements · Build my Earnings Passport")).toBeVisible();
  await page.getByLabel("What we may read").selectOption("platform_statement");
  await page.getByRole("button", { name: "Give consent" }).click();
  await expect(page.getByText("Platform payout statements · Build my Earnings Passport")).toBeVisible();
  await expect(page.getByText("Active", { exact: true })).toHaveCount(2);

  // A3 upload the bank statement and both payout statements
  await page.getByRole("link", { name: "Sources", exact: true }).click();
  await page.getByLabel(/Last 4 digits/).fill("8642");
  await page.getByLabel(/Name for this source/).fill("Vijayanagar savings");
  await upload(page, "bank_statement.csv");
  await expect(page.getByText("Statement read: 560 rows added.")).toBeVisible();
  await upload(page, "swiggy_payouts.csv", "Swiggy");
  await expect(page.getByText("Statement read: 56 rows added.")).toBeVisible();
  await upload(page, "rapido_payouts.csv", "Rapido");
  await expect(page.getByText("Statement read: 56 rows added.")).toBeVisible();
  await expect(page.getByText("Ready", { exact: true })).toHaveCount(3);
  await expect(page.getByText("0 rows skipped")).toHaveCount(3);

  // A4 reconciliation in the transaction list
  await page.getByLabel("Type").selectOption("earned");
  await expect(page.locator("#transactions tbody tr").first()).toContainText("Matched");

  // A5 passport
  await page.getByRole("link", { name: "My Passport", exact: true }).click();
  const card = page.locator("section[aria-label='EarnScore']");
  await expect(card.locator(".text-3xl")).toHaveText("75");
  await expect(card.getByLabel("Band B")).toBeVisible();
  await expect(card).toContainText("High confidence");
  await expect(card).toContainText("₹776");
  await expect(page.getByText("Payouts matched to bank credits")).toBeVisible();
  await expect(page.getByText("111 / 112")).toBeVisible();

  // A6 pillar and reason evidence
  await page.getByRole("button", { name: /^Capacity/ }).click();
  await expect(page.getByRole("dialog").locator("tbody tr").first()).toBeVisible();
  await page.getByRole("button", { name: "Close" }).click();
  await page.getByRole("button", { name: /See transactions/ }).first().click();
  await expect(page.getByRole("dialog").locator("tbody tr").first()).toBeVisible();
  await page.getByRole("button", { name: "Close" }).click();

  // A7 Tamil, Hindi, read aloud
  await page.getByLabel("Language").selectOption("ta");
  await expect(page.getByRole("heading", { name: "என் வருமான பாஸ்போர்ட்" })).toBeVisible();
  await expect(card).toContainText("அதிக நம்பகத்தன்மை");
  await expect(page.getByRole("button", { name: "உரக்கப் படி" })).toBeVisible();
  await page.getByLabel("மொழி").selectOption("hi");
  await expect(page.getByRole("heading", { name: "मेरा कमाई पासपोर्ट" })).toBeVisible();
  await expect(page.getByRole("button", { name: "पढ़कर सुनाएँ" })).toBeVisible();
  await page.getByLabel("भाषा").selectOption("en");

  // A8 how to improve
  await page.getByRole("link", { name: "How to improve", exact: true }).click();
  await expect(page.getByText("Now: Band B (75)")).toBeVisible();
  await expect(page.getByText("Hours worked, number of platforms and how much you earn.")).toBeVisible();

  // A9 share with a lender
  await page.getByRole("link", { name: "Share", exact: true }).click();
  await expect(page.getByLabel("Lender")).toHaveValue(/\d+/);
  await page.getByLabel("Purpose of the loan").fill("Second-hand scooter");
  await page.getByRole("button", { name: "Share my passport" }).click();
  await expect(page.getByRole("alert").or(page.locator(".card")).getByText("Submitted").first()).toBeVisible();
  await expect(page.getByText(/Link active · Link expires/)).toBeVisible();

  // A10 dispute
  await page.getByRole("link", { name: "Raise a dispute" }).click();
  await expect(page.getByLabel("About")).toHaveValue("decision");
  await page.getByLabel("What is wrong?").fill("My Rapido payouts from March look lower than what I received.");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("Your dispute was sent.")).toBeVisible();
  await expect(page.getByText("Open", { exact: true })).toBeVisible();
  await logout(page);
});

test("B. officer path", async ({ page }) => {
  await login(page, officer().email, officer().password);
  await expect(page.getByRole("heading", { name: "Applications" })).toBeVisible();
  await page.getByRole("link", { name: me.name }).click();
  await expect(page.getByRole("heading", { name: me.name })).toBeVisible();
  await expect(page.getByText("Model v1")).toBeVisible();

  // B3 pillar evidence and reason codes
  await page.getByRole("button", { name: /^Capacity/ }).click();
  await expect(page.getByRole("dialog")).toContainText("Capacity pillar");
  await expect(page.getByRole("dialog").locator("tbody tr").first()).toBeVisible();
  await page.getByRole("button", { name: "Close" }).click();

  // B4 reconciliation drill-down: each bank credit beside its platform payout
  await page.getByRole("button", { name: /Payouts matched to bank/ }).click();
  await expect(page.getByRole("dialog")).toContainText("Bank credits matched to platform payouts");
  await expect(page.getByRole("dialog").getByRole("columnheader", { name: "Matched payout" })).toBeVisible();
  await expect(page.getByRole("dialog").locator("tbody tr").first()).toContainText(/Swiggy|Rapido/);
  await page.getByRole("button", { name: "Close" }).click();

  // B5 seasonality and loan shape
  await expect(page.getByRole("heading", { name: /^Seasonality: raw swing \d+(\.\d)?% vs unexplained swing \d+(\.\d)?% after adjustment/ })).toBeVisible();
  await expect(page.getByText("Suggested loan shape")).toBeVisible();
  await expect(page.getByText("most common payout day")).toBeVisible();

  // B6 decision: a reason code is mandatory; Modify differs from the suggestion -> override
  await expect(page.getByText("Suggested outcome: Approve.")).toBeVisible();
  await page.getByLabel("Modify").check();
  await expect(page.getByText(/will be recorded in the override log/)).toBeVisible();
  await page.getByRole("button", { name: "Record decision" }).click();
  await expect(page.getByText("Choose a reason code.")).toBeVisible();
  await page.getByLabel("Reason code").selectOption("ADD_SKIP_WEEK");
  await page.getByLabel("Note").fill("Approved with a skip-week in the slow monsoon week.");
  await page.getByRole("button", { name: "Record decision" }).click();
  await expect(page.getByText(/Modify · ADD_SKIP_WEEK · Credit Officer/)).toBeVisible();
  await expect(page.getByText("Override of the suggested outcome")).toBeVisible();

  // B7 dispute response
  await page.getByRole("link", { name: "Disputes", exact: true }).click();
  const row = page.getByRole("row", { name: new RegExp(me.name) });
  await row.getByRole("button", { name: "Respond" }).click();
  await page.getByLabel("Response to the worker").fill("We are checking your Rapido payouts against the bank credits.");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(row).toContainText("In Review");

  // B8 monthly refresh -> early warning
  await page.getByRole("link", { name: "Portfolio", exact: true }).click();
  await page.getByRole("button", { name: "Run monthly refresh" }).click();
  await expect(page.getByText(/Refreshed \d+ loans; 1 alert\(s\)\./)).toBeVisible();
  const ganesh = page.getByRole("row", { name: /Ganesh Pillai/ });
  await expect(ganesh).toContainText("F20 −60%");
  await expect(ganesh).toContainText("suggest restructuring");
  await ganesh.getByRole("link", { name: "Ganesh Pillai" }).click();
  await expect(page.getByText(/Bad-week floor fell 60%/)).toBeVisible();
  await logout(page);
});

test("C. back to the worker", async ({ page }) => {
  await login(page, me.email, me.password);
  await page.getByRole("link", { name: "Share", exact: true }).click();
  await expect(page.getByText("Lender's decision: Approved with changes")).toBeVisible();
  await expect(page.getByText("add skip week")).toBeVisible();

  await page.getByRole("link", { name: "Disputes", exact: true }).click();
  await expect(page.getByText("In review", { exact: true })).toBeVisible();
  await expect(page.getByText("We are checking your Rapido payouts against the bank credits.")).toBeVisible();

  // revoke the platform consent: both payout sources withdrawn, score recomputed from the bank statement alone
  await page.getByRole("link", { name: "Consents", exact: true }).click();
  const plat = page.locator("li", { hasText: "Platform payout statements · Build my Earnings Passport" });
  await plat.getByRole("button", { name: "Revoke" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Revoke" }).click();
  await expect(page.getByText("Consent revoked. 2 source(s) withdrawn, 1 share link(s) closed.")).toBeVisible();
  await expect(plat).toContainText("Revoked");

  await page.getByRole("link", { name: "Sources", exact: true }).click();
  await expect(page.getByText("Consent withdrawn")).toHaveCount(2);
  await expect(page.getByText(/Scheduled for deletion on/)).toHaveCount(2);

  await page.getByRole("link", { name: "My Passport", exact: true }).click();
  await expect(page.getByText("Sources: 1 (3 needed)")).toBeVisible();
  await expect(page.getByText("0 / 0")).toBeVisible();

  // delete the bank source: no data left
  await page.getByRole("link", { name: "Sources", exact: true }).click();
  const bank = page.locator("li", { hasText: "Vijayanagar savings" });
  await bank.getByRole("button", { name: "Delete" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Delete" }).click();
  await expect(page.locator("li", { hasText: "Vijayanagar savings" })).toHaveCount(0);
  await page.getByRole("link", { name: "My Passport", exact: true }).click();
  await expect(page.getByText("Your passport is waiting for data")).toBeVisible();

  // the decided application keeps its frozen report
  await page.getByRole("link", { name: "Share", exact: true }).click();
  await expect(page.getByText("Lender's decision: Approved with changes")).toBeVisible();
  await expect(page.getByText("Link closed")).toBeVisible();
  await logout(page);
});

test("D. auditor / admin path", async ({ page }) => {
  await login(page, admin().email, admin().password);
  await expect(page.getByRole("heading", { name: "Model cards" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "v1", exact: true })).toBeVisible();
  await expect(page.getByText("Passed validation").first()).toBeVisible();

  await page.getByRole("link", { name: "Validation", exact: true }).click();
  await expect(page.getByText("0.877")).toBeVisible();
  await expect(page.getByText("3.26×")).toBeVisible();
  await expect(page.getByRole("heading", { name: "About these results" })).toBeVisible();

  await page.getByRole("link", { name: "Fairness", exact: true }).click();
  await expect(page.getByText(/Proxy check/)).toBeVisible();

  await page.getByRole("link", { name: "Drift", exact: true }).click();
  await expect(page.getByText(/Population stability index/)).toBeVisible();

  await page.getByRole("link", { name: "Override log", exact: true }).click();
  await page.getByLabel("Overrides only").check();
  const ov = page.getByRole("row", { name: new RegExp(me.name) });
  await expect(ov).toContainText("Modify · override");
  await expect(ov).toContainText("ADD_SKIP_WEEK");

  await page.getByRole("link", { name: "Audit log", exact: true }).click();
  await page.getByLabel("Action").selectOption("report.read");
  await expect(page.locator("tbody tr").first()).toContainText("Credit Officer");

  await page.getByRole("link", { name: "Users & lenders", exact: true }).click();
  await page.getByLabel("Search name or email").fill(me.email);
  const u = page.getByRole("row", { name: new RegExp(me.email) });
  await u.getByRole("button", { name: "Deactivate" }).click();
  await expect(u).toContainText("Deactivated");
  await logout(page);

  // a deactivated account cannot sign in
  await page.goto("/login");
  await page.getByLabel("Email").fill(me.email);
  await page.getByLabel("Password").fill(me.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("This account has been deactivated. Contact support.")).toBeVisible();

  await login(page, admin().email, admin().password);
  await page.getByRole("link", { name: "Users & lenders", exact: true }).click();
  await page.getByLabel("Search name or email").fill(me.email);
  await page.getByRole("row", { name: new RegExp(me.email) }).getByRole("button", { name: "Reactivate" }).click();
  await expect(page.getByRole("row", { name: new RegExp(me.email) })).toContainText("Active");
  await logout(page);
});

test("E1. low confidence worker sees no band verdict", async ({ page }) => {
  await login(page, "suresh.kumar@example.com", workerPw());
  const card = page.locator("section[aria-label='EarnScore']");
  await expect(card).toContainText("Low confidence");
  await expect(card.getByLabel(/^Band /)).toHaveCount(0);
  await expect(card).toContainText("Your band is not shown as a verdict until we have enough data.");
  await expect(card).toContainText("Not enough data yet — add: your platform payout statement");
  await page.getByRole("link", { name: "How to improve", exact: true }).click();
  await expect(page.getByText(/Your confidence is Low, so lenders will review your case by hand/)).toBeVisible();
  await logout(page);
});

test("E2. flagged worker goes to manual review", async ({ page }) => {
  // Vijay's generated application went to the other lender; share with Nilavu so this officer can see it
  await login(page, "vijay.anand@example.com", workerPw());
  await page.getByRole("link", { name: "Share", exact: true }).click();
  await page.getByRole("button", { name: "Share my passport" }).click();
  await expect(page.getByText("With a credit officer for review").first()).toBeVisible();
  await logout(page);

  await login(page, officer().email, officer().password);
  await page.getByLabel("Routing").selectOption("true");
  await page.getByRole("link", { name: "Vijay Anand" }).click();
  await expect(page.getByText(/Manual review required:.*Anti-gaming flag/)).toBeVisible();
  await expect(page.getByText("Credits mirroring own-account transfers · 4")).toBeVisible();
  await page.getByRole("listitem").filter({ hasText: "Credits mirroring own-account transfers" }).getByRole("button", { name: "Open transactions" }).click();
  await expect(page.getByRole("dialog").locator("tbody tr")).toHaveCount(4);
  await page.getByRole("button", { name: "Close" }).click();
  await expect(page.getByText("Suggested outcome: no suggestion (manual review).")).toBeVisible();
  await logout(page);
});

test("E3. closed share link: the officer can no longer open the report", async ({ page }) => {
  await login(page, "lakshmi.devi@example.com", workerPw());
  await page.getByRole("link", { name: "Share", exact: true }).click();
  await page.getByRole("button", { name: "Revoke link" }).first().click();
  await page.getByRole("dialog").getByRole("button", { name: "Revoke link" }).click();
  await expect(page.getByText("Link closed")).toBeVisible();
  await logout(page);

  await login(page, officer().email, officer().password);
  const row = page.getByRole("row", { name: /Lakshmi Devi/ });
  await expect(row).toContainText("Share link closed");
  await row.getByRole("link", { name: "Lakshmi Devi" }).click();
  await expect(page.getByText("The worker's share link has expired or was revoked, so this report is no longer available.")).toBeVisible();
  await logout(page);
});

test("E4. wrong-role URLs", async ({ page }) => {
  await page.goto("/officer");
  await expect(page).toHaveURL(/\/login\?next=%2Fofficer/);
  await login(page, "meena.sundaram@example.com", workerPw());
  await page.goto("/admin/users");
  await expect(page).toHaveURL(/\/worker$/);
  const res = await page.request.get("/api/admin/users");
  expect(res.status()).toBe(403);
  expect((await res.json()).detail).toBe("You do not have access to this area.");
  await logout(page);
});

test("E5. invalid and unsupported files, and a layout that needs a column check", async ({ page }) => {
  await login(page, me.email, me.password);
  await page.getByRole("link", { name: "Sources", exact: true }).click();

  await upload(page, "statement_photo.jpg");
  await expect(page.getByText(/Photos of statements are not supported/)).toBeVisible();

  await upload(page, "scanned_statement.pdf");
  await expect(page.getByText(/This PDF has no readable text \(it looks like a scanned image\)/).first()).toBeVisible();

  await upload(page, "corrupted_statement.xlsx");
  await expect(page.getByText("This Excel file could not be opened. Check that it is a valid .xlsx file.").first()).toBeVisible();
  await expect(page.getByText("Could not read", { exact: true })).toHaveCount(2);

  await upload(page, "bank_statement_other_layout.csv");
  await expect(page.getByRole("dialog")).toContainText("Check the columns");
  await page.getByLabel("Debit (money out)").selectOption("Out");
  await page.getByLabel("Credit (money in)").selectOption("In");
  await page.getByRole("button", { name: "Read with these columns" }).click();
  await expect(page.getByText("Statement read: 560 rows added.")).toBeVisible();
  await page.getByRole("link", { name: "My Passport", exact: true }).click();
  await expect(page.locator("section[aria-label='EarnScore'] .text-3xl")).toHaveText(/\d+/);
  await logout(page);
});

test("E6. wrong password and session expiry", async ({ page, context }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("meena.sundaram@example.com");
  await page.getByLabel("Password").fill("not-the-password-1");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Email or password is incorrect.")).toBeVisible();

  await login(page, "meena.sundaram@example.com", workerPw());
  await expect(page.getByRole("heading", { name: "My Earnings Passport" })).toBeVisible();
  // what the browser does when the 12-hour session cookie expires
  const keep = (await context.cookies()).filter((c) => c.name !== "es_session");
  await context.clearCookies();
  await context.addCookies(keep);
  await page.getByRole("link", { name: "Sources", exact: true }).click();
  await expect(page).toHaveURL(/\/login\?next=%2Fworker%2Fsources/);
});
