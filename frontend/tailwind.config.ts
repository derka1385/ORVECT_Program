import type { Config } from "tailwindcss";
export default {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        orvect: {
          graphite: "#101214",
          mineral: "#F2F1ED",
          orange: "#FF5C28",
          alloy: "#B8BABD",
        },
        canvas: "#e7e9ec",   // bureau gris clair
        surface: "#ffffff",  // panneaux blancs
        panel: "#f1f3f5",    // encarts gris clair
        line: "#c3cad2",     // bordures fines nettes
        primary: "#1c5fb0",  // bleu logiciel classique
        warning: "#b45309",
        danger: "#c0392b",
        success: "#1a7f37",
        info: "#0b6aa2",
        muted: "#5c6773",
        ink: "#1a1f26",      // texte principal
      },
      fontFamily: {
        ui: ['"Space Grotesk"', "Arial", "Helvetica", "sans-serif"],
        mono: ['Consolas', '"Courier New"', "ui-monospace", "monospace"],
      },
      borderRadius: {
        DEFAULT: "2px",
        md: "2px",
        lg: "2px",
        xl: "3px",
        "2xl": "3px",
      },
      boxShadow: {
        panel: "0 1px 2px rgba(16,24,40,.08)",
        sunken: "inset 0 1px 2px rgba(16,24,40,.10)",
      },
    },
  },
  plugins: [],
} satisfies Config;
