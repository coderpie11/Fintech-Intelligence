"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import SearchBar from "./SearchBar";
import ThemeToggle from "./ThemeToggle";
import MarketClock from "./MarketClock";
import BrandMark from "./BrandMark";
import { NAV_GROUPS, NAV_DIRECT } from "@/lib/nav";

function isActive(path: string, href: string) {
  return path === href || path.startsWith(href + "/");
}

export default function Navbar() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  const [group, setGroup] = useState<string | null>(null);
  const path = usePathname();

  useEffect(() => {
    const h = () => setScrolled(window.scrollY > 6);
    h();
    window.addEventListener("scroll", h, { passive: true });
    return () => window.removeEventListener("scroll", h);
  }, []);

  useEffect(() => { setOpen(false); setGroup(null); }, [path]);

  const groupActive = (items: { href: string }[]) =>
    items.some((i) => isActive(path, i.href));

  return (
    <header className={`fixed top-0 inset-x-0 z-[60] transition-all ${scrolled || open ? "nav-solid" : ""}`}
            style={!scrolled && !open ? { background: "color-mix(in srgb, var(--bg) 72%, transparent)", backdropFilter: "blur(10px)" } : undefined}>
      <div className="mx-auto max-w-[1600px] px-3 sm:px-5">
        <div className="flex h-[62px] items-center gap-2.5">
          {/* brand — plain wordmark, no dropdown on the site name */}
          <Link href="/" className="shrink-0 group flex items-center gap-2.5" aria-label="Fintech Intelligence home">
            <BrandMark size={32} />
            <span className="leading-none">
              <span className="block text-[14.5px] font-black tracking-tight">
                Fintech <span className="accent">Intelligence</span>
              </span>
              <span className="hidden sm:block muted text-[8.5px] font-semibold tracking-[0.2em] uppercase mt-1">
                Institutional Market Terminal
              </span>
            </span>
          </Link>

          {/* desktop nav — three grouped menus plus four direct desks */}
          <nav aria-label="Desks"
               className="relative hidden lg:flex flex-1 min-w-0 items-center gap-0.5 px-1">
            {NAV_GROUPS.map((g) => {
              const active = groupActive(g.items);
              const isOpen = group === g.key;
              return (
                <div key={g.key} className="relative"
                     onMouseEnter={() => setGroup(g.key)}
                     onMouseLeave={() => setGroup(null)}>
                  <button
                    type="button"
                    aria-haspopup="menu"
                    aria-expanded={isOpen}
                    onClick={() => setGroup(isOpen ? null : g.key)}
                    className={`shrink-0 whitespace-nowrap rounded-md px-2.5 py-1.5 text-[12px] font-semibold transition-colors inline-flex items-center gap-1 ${
                      active ? "accent" : "muted hover:text-[var(--ink)]"
                    }`}
                    style={active ? {
                      background: "color-mix(in srgb, var(--accent) 12%, transparent)",
                      boxShadow: "inset 0 -1.5px 0 var(--accent)",
                    } : undefined}
                  >
                    {g.label}
                    <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                         strokeWidth="3" strokeLinecap="round" aria-hidden
                         style={{ transform: isOpen ? "rotate(180deg)" : undefined, transition: "transform .15s" }}>
                      <path d="m6 9 6 6 6-6" />
                    </svg>
                  </button>
                  {isOpen && (
                    <div className="absolute left-0 top-full z-[70] pt-1.5">
                      <div className="card min-w-[272px] p-1.5 shadow-2xl">
                        {g.items.map((item) => {
                          const itemActive = isActive(path, item.href);
                          return (
                            <Link key={item.key} href={item.href}
                                  className="block rounded-lg px-3 py-2 transition-colors hover:bg-[var(--surface-2)]"
                                  style={itemActive ? { background: "color-mix(in srgb, var(--accent) 10%, transparent)" } : undefined}>
                              <div className={`text-[12.5px] font-bold ${itemActive ? "accent" : ""}`}
                                   style={itemActive ? undefined : { color: "var(--ink)" }}>
                                {item.label}
                              </div>
                              {item.desc && <div className="muted text-[10.5px] mt-0.5">{item.desc}</div>}
                            </Link>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}

            {NAV_DIRECT.map((item) => {
              const active = isActive(path, item.href);
              return (
                <Link
                  key={item.key}
                  href={item.href}
                  data-active={active}
                  aria-current={active ? "page" : undefined}
                  className={`shrink-0 whitespace-nowrap rounded-md px-2.5 py-1.5 text-[12px] font-semibold transition-colors ${
                    active ? "accent" : "muted hover:text-[var(--ink)]"
                  }`}
                  style={active ? {
                    background: "color-mix(in srgb, var(--accent) 12%, transparent)",
                    boxShadow: "inset 0 -1.5px 0 var(--accent)",
                  } : undefined}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <div className="ml-auto flex items-center gap-1.5 shrink-0">
            <SearchBar />
            <span className="hidden md:inline-flex">
              <MarketClock compact />
            </span>
            <ThemeToggle />
            <button
              className="btn-secondary !px-2.5 !py-2 lg:hidden"
              aria-label={open ? "Close menu" : "Open menu"}
              aria-expanded={open}
              onClick={() => setOpen(!open)}
            >
              {open ? (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
                  <path d="M6 6l12 12M18 6L6 18" />
                </svg>
              ) : (
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
                  <path d="M3 6h18M3 12h18M3 18h18" />
                </svg>
              )}
            </button>
          </div>
        </div>

        {/* mobile / tablet menu */}
        {open && (
          <div className="lg:hidden pb-4 pt-1 max-h-[calc(100vh-70px)] overflow-y-auto"
               style={{ borderTop: "1px solid var(--line)" }}>
            <div className="flex flex-wrap items-center gap-2 py-3 md:hidden">
              <MarketClock showSeconds />
            </div>

            {NAV_GROUPS.map((g) => (
              <div key={g.key} className="mt-3">
                <div className="muted text-[9.5px] font-bold uppercase tracking-[0.16em] px-1 mb-1.5">{g.label}</div>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-1.5">
                  {g.items.map((item) => {
                    const active = isActive(path, item.href);
                    return (
                      <Link key={item.key} href={item.href}
                            className={`rounded-lg px-3 py-2.5 text-[12.5px] font-semibold ${active ? "accent" : ""}`}
                            style={{
                              border: "1px solid var(--line)",
                              background: active ? "color-mix(in srgb, var(--accent) 10%, var(--surface))" : "var(--surface)",
                            }}>
                        {item.label}
                      </Link>
                    );
                  })}
                </div>
              </div>
            ))}

            <div className="mt-3">
              <div className="muted text-[9.5px] font-bold uppercase tracking-[0.16em] px-1 mb-1.5">Tools</div>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-1.5">
                {NAV_DIRECT.map((item) => {
                  const active = isActive(path, item.href);
                  return (
                    <Link key={item.key} href={item.href}
                          className={`rounded-lg px-3 py-2.5 text-[12.5px] font-semibold ${active ? "accent" : ""}`}
                          style={{
                            border: "1px solid var(--line)",
                            background: active ? "color-mix(in srgb, var(--accent) 10%, var(--surface))" : "var(--surface)",
                          }}>
                      {item.label}
                    </Link>
                  );
                })}
              </div>
            </div>
          </div>
        )}
      </div>
    </header>
  );
}
