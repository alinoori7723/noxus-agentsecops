/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#070b14",
          900: "#0b1120",
          850: "#0f1729",
          800: "#141d33",
          700: "#1c2741",
          600: "#26344f",
        },
        line: {
          DEFAULT: "#22304d",
          soft: "#1a2540",
        },
        accent: {
          DEFAULT: "#6366f1",
          soft: "#818cf8",
        },
      },
      fontFamily: {
        sans: [
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Monaco",
          "Consolas",
          "monospace",
        ],
      },
      boxShadow: {
        panel: "0 24px 64px rgba(0, 0, 0, 0.45)",
        glow: "0 18px 50px rgba(99, 102, 241, 0.25)",
      },
    },
  },
  plugins: [],
};
