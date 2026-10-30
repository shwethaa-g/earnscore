import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./en";
import hi from "./hi";
import ta from "./ta";

export const LANGS = ["en", "ta", "hi"] as const;
export type Lang = (typeof LANGS)[number];

function initial(): Lang {
  try {
    const v = localStorage.getItem("es_lang");
    if (v === "en" || v === "ta" || v === "hi") return v;
  } catch {
    /* storage unavailable */
  }
  return "en";
}

i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, ta: { translation: ta }, hi: { translation: hi } },
  lng: initial(),
  fallbackLng: "en",
  interpolation: { escapeValue: false },
});

i18n.on("languageChanged", (l) => {
  document.documentElement.lang = l;
  try {
    localStorage.setItem("es_lang", l);
  } catch {
    /* storage unavailable */
  }
});
document.documentElement.lang = i18n.language;

export default i18n;
