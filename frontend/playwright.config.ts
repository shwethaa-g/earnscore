import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: { timeout: 15_000 },
  retries: 0,
  workers: 1, // serial: the auth rate limiter allows 10 sign-ins per minute per IP
  reporter: [["list"]],
  use: { baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:8000", trace: "retain-on-failure", screenshot: "only-on-failure", viewport: { width: 1280, height: 900 } },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
