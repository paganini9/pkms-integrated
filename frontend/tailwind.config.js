/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // 검증 답변(신뢰) vs LLM 단독(미검증) 대비 팔레트
        verified: { bg: "#ecfdf5", border: "#10b981", text: "#065f46" },
        unverified: { bg: "#fff7ed", border: "#f59e0b", text: "#92400e" },
        amber: { bg: "#fffbeb", border: "#f59e0b", text: "#92400e" },
      },
    },
  },
  plugins: [],
};
