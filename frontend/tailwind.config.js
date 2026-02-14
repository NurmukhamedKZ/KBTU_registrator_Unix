/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ub: {
          bg: "#090B10",
          panel: "#111725",
          panelSoft: "#181F30",
          border: "#2A344E",
          text: "#E8EDF7",
          muted: "#9CA9C5",
          blue: "#2F6CFF",
          violet: "#7747F9",
          green: "#2F8D66",
          amber: "#A8711C",
          danger: "#E05353",
        },
      },
      boxShadow: {
        ub: "0 12px 40px rgba(0, 0, 0, 0.35)",
      },
    },
  },
  plugins: [],
};
