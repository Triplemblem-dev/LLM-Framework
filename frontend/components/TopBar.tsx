"use client";

import { Domain, ModelInfo, SubDomain } from "../lib/types";
import { HelpIcon, MenuIcon, PanelRightIcon } from "./icons";
import { ThemeSwitch } from "./ThemeSwitch";

interface TopBarProps {
  domain: Domain | null;
  subdomain: SubDomain | null;
  model: ModelInfo | null;
  onToggleLeft: () => void;
  onToggleRight: () => void;
  onOpenHelp: () => void;
}

export function TopBar({ domain, subdomain, model, onToggleLeft, onToggleRight, onOpenHelp }: TopBarProps) {
  return (
    <header className="topbar">
      <button className="icon-btn rail-toggle" onClick={onToggleLeft} title="Toggle domains" aria-label="Toggle domains panel">
        <MenuIcon />
      </button>
      <div className="brand">
        <svg className="mark" viewBox="0 0 20 20" fill="none">
          <rect x="1.5" y="1.5" width="17" height="17" rx="4" stroke="var(--accent)" strokeWidth="1.5" />
          <rect x="6" y="6" width="8" height="8" rx="2" stroke="var(--accent)" strokeWidth="1.5" />
        </svg>
        <div className="brand-text">
          <b>LLM Framework</b>
          <span>local workspace</span>
        </div>
      </div>
      <div className="crumbs">
        <div className="crumb model">
          <span className="k">Model</span>
          <span className="v">{model ? model.name : "None selected"}</span>
        </div>
        <span className="crumb-sep">/</span>
        <div className="crumb">
          <span className="k">Domain</span>
          <span className="v">{domain ? domain.name : "None"}</span>
        </div>
        {subdomain && (
          <>
            <span className="crumb-sep">/</span>
            <div className="crumb">
              <span className="k">Sub</span>
              <span className="v">{subdomain.name}</span>
            </div>
          </>
        )}
      </div>
      <div className="top-actions">
        <ThemeSwitch />
        <button className="icon-btn" onClick={onOpenHelp} title="How this workspace works" aria-label="Open help">
          <HelpIcon />
        </button>
        <button className="icon-btn rail-toggle" onClick={onToggleRight} title="Toggle inspector" aria-label="Toggle inspector panel">
          <PanelRightIcon />
        </button>
      </div>
    </header>
  );
}
