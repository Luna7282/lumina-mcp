/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        background: "#0a0a0f",
        surface: "#13131a",
        border: "#1e1e2e",
        accent: "#7c3aed",
        "accent-hover": "#6d28d9",
        "text-primary": "#f1f5f9",
        "text-muted": "#64748b",
        success: "#10b981",
        error: "#ef4444",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
