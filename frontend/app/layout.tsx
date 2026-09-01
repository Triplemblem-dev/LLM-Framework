import type { Metadata } from "next";
import Script from "next/script";
import "./globals.css";

const THEME_INITIALIZER = `
(() => {
  const storageKey = "llm-framework-theme";
  let theme = "light";
  try {
    const savedTheme = window.localStorage.getItem(storageKey);
    theme = savedTheme === "light" || savedTheme === "dark"
      ? savedTheme
      : window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light";
  } catch {
    theme = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  document.documentElement.dataset.theme = theme;
})();
`;

export const metadata: Metadata = {
  title: "LLM Framework — Workspace",
  description: "Domain/sub-domain workspace for the self-hosted LLM framework.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        {children}
        <Script id="theme-initializer" strategy="beforeInteractive">
          {THEME_INITIALIZER}
        </Script>
      </body>
    </html>
  );
}
