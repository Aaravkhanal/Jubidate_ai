import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}"
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-inter)", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["var(--font-space)", "var(--font-inter)", "ui-sans-serif", "system-ui", "sans-serif"]
      },
      colors: {
        sm: {
          primary: "#0a0a1a",
          secondary: "#12121f",
          surface: "#1a1a2e",
          elevated: "#222240",
          indigo: "#6366f1",
          "indigo-light": "#818cf8",
          cyan: "#06b6d4",
          "cyan-light": "#22d3ee",
          violet: "#a78bfa",
          pro: "#10b981",
          "pro-light": "#34d399",
          con: "#f43f5e",
          "con-light": "#fb7185"
        }
      },
      borderRadius: {
        "sm-sm": "8px",
        "sm-md": "12px",
        "sm-lg": "16px",
        "sm-xl": "20px"
      },
      animation: {
        "sm-fade-in": "sm-fade-in 0.4s ease-out forwards",
        "sm-slide-up": "sm-slide-up 0.5s ease-out forwards",
        "sm-float": "sm-float 3s ease-in-out infinite",
        "sm-pulse-glow": "sm-pulse-glow 2s ease-in-out infinite",
        "sm-gradient-flow": "sm-gradient-flow 4s ease infinite"
      }
    }
  },
  plugins: []
};

export default config;
