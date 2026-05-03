"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Bot, FlaskConical } from "lucide-react";

const tabs = [
  {
    href: "/benchmark",
    label: "Benchmarking",
    description: "LLM replay lab",
    icon: FlaskConical,
  },
  {
    href: "/arena",
    label: "Arena",
    description: "Paid room beta",
    icon: Bot,
  },
];

export function ModeTabs() {
  const pathname = usePathname();

  return (
    <nav className="mode-tabs" aria-label="LLM Survivor modes">
      <div className="mode-tabs-inner">
        <Link className="mode-brand" href="/benchmark" aria-label="LLM Survivor benchmark home">
          <span>LLM Survivor</span>
        </Link>
        <div className="mode-tab-list">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = pathname === tab.href || pathname.startsWith(`${tab.href}/`);
            return (
              <Link
                key={tab.href}
                href={tab.href}
                className={isActive ? "mode-tab active" : "mode-tab"}
                aria-current={isActive ? "page" : undefined}
              >
                <Icon size={17} />
                <span>
                  <strong>{tab.label}</strong>
                  <small>{tab.description}</small>
                </span>
              </Link>
            );
          })}
        </div>
      </div>
    </nav>
  );
}
