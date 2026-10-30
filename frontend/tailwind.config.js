/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: { sans: ["Inter", "system-ui", "Segoe UI", "Noto Sans Tamil", "Noto Sans Devanagari", "sans-serif"] },
      colors: {
        accent: { 50: "#effaf8", 100: "#d6f2ed", 200: "#aee4db", 500: "#14917f", 600: "#0f7a6b", 700: "#0d6257", 800: "#0b4f47" },
      },
    },
  },
  plugins: [],
};
