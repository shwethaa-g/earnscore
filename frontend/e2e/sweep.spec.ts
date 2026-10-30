import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

// Visits every page for every role at desktop and 360 px: no horizontal scroll, no error states,
// no console errors, no forbidden wording. Screenshots go to test-results/sweep for review.
const __dirname = path.dirname(fileURLToPath(import.meta.url));
function env(name: string): string {
  if (process.env[name]) return process.env[name] as string;
  const line = fs.readFileSync(path.resolve(__dirname, "../../.env"), "utf8").split(/\r?\n/).find((l) => l.startsWith(`${name}=`));
  return (line ?? "").slice(name.length + 1).split(/\s+#/)[0].trim();
}
const out = path.resolve(__dirname, "../test-results/sweep");
const FORBIDDEN = /\b(demo|sample|mock|dummy|lorem|todo|test data)\b/i;

const ROLES = [
  { email: "karthik.subramanian@example.com", pw: env("SEED_WORKER_PASSWORD"), pages: ["/worker", "/worker/sources", "/worker/consents", "/worker/improve", "/worker/share", "/worker/disputes", "/worker/profile"] },
  { email: env("SEED_OFFICER_EMAIL"), pw: env("SEED_OFFICER_PASSWORD"), pages: ["/officer", "/officer/portfolio", "/officer/disputes"] },
  { email: env("SEED_ADMIN_EMAIL"), pw: env("SEED_ADMIN_PASSWORD"), pages: ["/admin", "/admin/validation", "/admin/fairness", "/admin/drift", "/admin/overrides", "/admin/audit", "/admin/users", "/admin/disputes"] },
];

for (const width of [1280, 360]) {
  for (const role of ROLES) {
    test(`${role.email} @${width}`, async ({ page }) => {
      const errors: string[] = [];
      page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
      page.on("pageerror", (e) => errors.push(e.message));
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/login");
      await page.getByLabel("Email").fill(role.email);
      await page.getByLabel("Password").fill(role.pw);
      await page.getByRole("button", { name: "Sign in" }).click();
      await page.waitForURL(/\/(worker|officer|admin)/);
      const pages = [...role.pages];
      if (role.pages[0] === "/officer") {
        await page.goto("/officer");
        await page.locator("tbody a").first().waitFor();
        pages.push(await page.locator("tbody a").first().getAttribute("href") as string);
      }
      for (const p of pages) {
        await page.goto(p);
        await page.waitForLoadState("networkidle");
        await expect(page.locator("main h1").first()).toBeVisible();
        await expect(page.getByText("Something went wrong")).toHaveCount(0);
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
        expect(overflow, `${p} horizontal overflow at ${width}px`).toBeLessThanOrEqual(1);
        const text = await page.locator("body").innerText();
        expect(FORBIDDEN.test(text), `${p} forbidden wording: ${text.match(FORBIDDEN)?.[0]}`).toBe(false);
        await page.screenshot({ path: path.join(out, `${width}${p.replace(/\//g, "_")}.png`), fullPage: true });
      }
      expect(errors, errors.join("\n")).toEqual([]);
    });
  }
}

for (const lang of ["ta", "hi"]) {
  test(`worker pages in ${lang} @360`, async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 900 });
    await page.goto("/login");
    await page.evaluate((l) => localStorage.setItem("es_lang", l), lang);
    await page.goto("/login");
    await page.locator("#email").fill("anitha.raman@example.com");
    await page.locator("#password").fill(env("SEED_WORKER_PASSWORD"));
    await page.locator("form button").click();
    await page.waitForURL(/\/worker/);
    for (const p of ROLES[0].pages) {
      await page.goto(p);
      await page.waitForLoadState("networkidle");
      await expect(page.locator("main h1").first()).toBeVisible();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(overflow, `${p} horizontal overflow in ${lang}`).toBeLessThanOrEqual(1);
      await page.screenshot({ path: path.join(out, `${lang}_360${p.replace(/\//g, "_")}.png`), fullPage: true });
    }
  });
}
