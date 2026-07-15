import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: "#06080F",
        surface: "#0A0D18",
        card: "#0F1220",
        "card-hover": "#141828",
        border: "#1A1D2E",
        "border-hover": "#252840",
        subtle: "#6B6F8A",
        muted: "#8A8FA8",
        gold: {
          DEFAULT: "#C9A84C",
          light: "#F0C060",
          dim: "#A8883A",
          subtle: "rgba(201,168,76,0.08)",
          muted: "rgba(201,168,76,0.15)",
          glow: "rgba(201,168,76,0.25)",
        },
        accent: {
          DEFAULT: "#C9A84C",
          hover: "#A8883A",
          light: "#F0C060",
          subtle: "rgba(201,168,76,0.08)",
          muted: "rgba(201,168,76,0.15)",
        },
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
        serif: ["var(--font-playfair)", "Georgia", "serif"],
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
      boxShadow: {
        "glow-sm": "0 0 0 1px rgba(201,168,76,0.15), 0 2px 8px rgba(201,168,76,0.08)",
        "glow": "0 0 0 1px rgba(201,168,76,0.22), 0 4px 20px rgba(201,168,76,0.12)",
        "glow-lg": "0 0 0 1px rgba(201,168,76,0.25), 0 8px 40px rgba(201,168,76,0.18)",
        "card": "0 1px 3px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.03)",
        "card-hover": "0 4px 20px rgba(0,0,0,0.6), 0 0 0 1px rgba(201,168,76,0.08)",
        "inner": "inset 0 1px 0 rgba(255,255,255,0.03)",
        "gold-inner": "inset 0 1px 0 rgba(201,168,76,0.06)",
      },
      backgroundImage: {
        "gradient-radial": "radial-gradient(var(--tw-gradient-stops))",
        "gradient-gold": "linear-gradient(135deg, #C9A84C, #F0C060)",
        "gradient-gold-dark": "linear-gradient(135deg, #A8883A, #C9A84C)",
        "shimmer": "linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.03) 50%, transparent 100%)",
        "shimmer-gold": "linear-gradient(90deg, transparent 0%, rgba(201,168,76,0.06) 50%, transparent 100%)",
        "mesh-hero": "radial-gradient(ellipse 80% 50% at 50% -10%, rgba(201,168,76,0.12) 0%, transparent 60%), radial-gradient(ellipse 60% 40% at 80% 60%, rgba(168,136,58,0.08) 0%, transparent 50%)",
        "mesh-card": "radial-gradient(ellipse 100% 100% at 50% 0%, rgba(201,168,76,0.04) 0%, transparent 70%)",
      },
      keyframes: {
        "slide-up": {
          from: { transform: "translateY(10px)", opacity: "0" },
          to: { transform: "translateY(0)", opacity: "1" },
        },
        "slide-down": {
          from: { transform: "translateY(-10px)", opacity: "0" },
          to: { transform: "translateY(0)", opacity: "1" },
        },
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        "scale-in": {
          from: { transform: "scale(0.96)", opacity: "0" },
          to: { transform: "scale(1)", opacity: "1" },
        },
        "pulse-soft": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.5" },
        },
        "shimmer": {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(100%)" },
        },
        "float": {
          "0%, 100%": { transform: "translateY(0px)" },
          "50%": { transform: "translateY(-6px)" },
        },
        "glow-pulse": {
          "0%, 100%": { boxShadow: "0 0 0 1px rgba(201,168,76,0.15), 0 0 20px rgba(201,168,76,0.08)" },
          "50%": { boxShadow: "0 0 0 1px rgba(201,168,76,0.3), 0 0 30px rgba(201,168,76,0.15)" },
        },
        "counter": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "slide-up": "slide-up 0.3s cubic-bezier(0.16,1,0.3,1)",
        "slide-down": "slide-down 0.3s cubic-bezier(0.16,1,0.3,1)",
        "fade-in": "fade-in 0.25s ease-out",
        "scale-in": "scale-in 0.2s cubic-bezier(0.16,1,0.3,1)",
        "pulse-soft": "pulse-soft 2.5s ease-in-out infinite",
        "shimmer": "shimmer 2.5s infinite",
        "float": "float 3s ease-in-out infinite",
        "glow-pulse": "glow-pulse 2.5s ease-in-out infinite",
        "counter": "counter 0.4s cubic-bezier(0.16,1,0.3,1) forwards",
      },
    },
  },
  plugins: [],
};

export default config;
