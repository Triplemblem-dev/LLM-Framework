"use client";

import { useEffect, useState } from "react";
import { MoonIcon, SunIcon } from "./icons";

type Theme = "light" | "dark";

const THEME_STORAGE_KEY = "llm-framework-theme";

function currentTheme(): Theme {
  if (document.documentElement.dataset.theme === "dark") return "dark";
  return "light";
}

export function ThemeSwitch() {
  const [theme, setTheme] = useState<Theme>("light");

  useEffect(() => {
    setTheme(currentTheme());
  }, []);

  function toggleTheme() {
    const nextTheme: Theme = currentTheme() === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = nextTheme;
    setTheme(nextTheme);
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, nextTheme);
    } catch {
      // The visual choice still applies when browser storage is unavailable.
    }
  }

  const nextTheme = theme === "dark" ? "light" : "dark";

  return (
    <button
      type="button"
      className="theme-switch"
      role="switch"
      aria-checked={theme === "dark"}
      aria-label={`Dark mode ${theme === "dark" ? "on" : "off"}. Switch to ${nextTheme} mode.`}
      title={`Switch to ${nextTheme} mode`}
      onClick={toggleTheme}
    >
      <span className="theme-switch-icon" aria-hidden="true">
        <SunIcon />
      </span>
      <span className="theme-switch-knob" aria-hidden="true" />
      <span className="theme-switch-icon" aria-hidden="true">
        <MoonIcon />
      </span>
    </button>
  );
}
