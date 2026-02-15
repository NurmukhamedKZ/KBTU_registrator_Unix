/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ub: {
          bg: "#000000",
          panel: "#1a1a1a",
          control: "#3a3a3b",
          text: "#d7d7d7",
          accent: "#005DC9",
        },
      },
      boxShadow: {
        ub: "0 12px 40px rgba(0, 0, 0, 0.35)",
      },
    },
  },
  plugins: [],
};
