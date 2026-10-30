import { describe, expect, it } from "vitest";
import { inr, pct, titleCase } from "./format";
import en from "../i18n/en";
import ta from "../i18n/ta";
import hi from "../i18n/hi";

function keys(o: any, p = ""): string[] {
  return Object.entries(o).flatMap(([k, v]) => (typeof v === "object" ? keys(v, `${p}${k}.`) : [`${p}${k}`]));
}

describe("format", () => {
  it("formats rupees with Indian grouping", () => {
    expect(inr(1234567)).toBe("₹12,34,567");
    expect(inr(null)).toBe("—");
  });
  it("formats percentages", () => {
    expect(pct(0.256)).toBe("26%");
  });
  it("title-cases snake case", () => {
    expect(titleCase("home_service")).toBe("Home Service");
  });
});

describe("translations", () => {
  it("Tamil and Hindi cover every English key", () => {
    const e = keys(en).sort();
    expect(keys(ta).sort()).toEqual(e);
    expect(keys(hi).sort()).toEqual(e);
  });
  it("keeps the same interpolation placeholders", () => {
    const flat = (o: any) => Object.fromEntries(keys(o).map((k) => [k, k.split(".").reduce((a: any, x) => a[x], o)]));
    const fe = flat(en), ft = flat(ta), fh = flat(hi);
    const ph = (s: string) => (s.match(/{{\w+}}/g) ?? []).sort().join(",");
    for (const k of Object.keys(fe)) {
      expect(ph(ft[k]), k).toBe(ph(fe[k]));
      expect(ph(fh[k]), k).toBe(ph(fe[k]));
    }
  });
  it("never uses forbidden wording in user-facing text", () => {
    const bad = /\b(demo|sample|mock|dummy|simulated|test data)\b/i;
    for (const d of [en, ta, hi]) for (const k of keys(d)) {
      const v = k.split(".").reduce((a: any, x) => a[x], d as any);
      expect(bad.test(v), `${k}: ${v}`).toBe(false);
    }
  });
});
