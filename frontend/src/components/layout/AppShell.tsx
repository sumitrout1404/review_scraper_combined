import { Menu, X } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { Brand } from './Brand';
import { FreshnessIndicator } from './Freshness';
import { NavLinks } from './NavLinks';

/** Fixed sidebar on large screens; a top bar with a slide-in drawer on small screens. */
export function AppShell() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const { pathname } = useLocation();

  const closeDrawer = useCallback(() => {
    setDrawerOpen(false);
    menuButtonRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!drawerOpen) return;
    closeButtonRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && closeDrawer();
    document.addEventListener('keydown', onKey);
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = '';
    };
  }, [drawerOpen, closeDrawer]);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);

  return (
    <div className="min-h-screen lg:pl-72">
      <a
        href="#main"
        className="focus-ring sr-only z-50 rounded-lg bg-white px-3 py-2 text-navy focus:not-sr-only focus:fixed focus:left-3 focus:top-3"
      >
        Skip to content
      </a>

      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 hidden w-72 flex-col bg-navy px-5 py-6 lg:flex">
        <Brand />
        <p className="mt-2 text-xs text-sand/70">Booking.com guest reviews · Sydney</p>
        <div className="mt-8 flex-1">
          <NavLinks />
        </div>
        <div className="border-t border-white/10 pt-4">
          <FreshnessIndicator variant="sidebar" />
        </div>
      </aside>

      {/* Mobile top bar */}
      <header className="sticky top-0 z-30 flex h-14 items-center justify-between bg-navy px-4 lg:hidden">
        <Brand compact />
        <button
          ref={menuButtonRef}
          type="button"
          onClick={() => setDrawerOpen(true)}
          aria-label="Open menu"
          aria-expanded={drawerOpen}
          aria-controls="mobile-drawer"
          className="focus-ring flex h-10 w-10 items-center justify-center rounded-xl text-white hover:bg-white/10 focus-visible:ring-offset-navy"
        >
          <Menu className="h-5 w-5" aria-hidden="true" />
        </button>
      </header>

      {/* Mobile drawer */}
      {drawerOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-navy/50 backdrop-blur-[2px]" aria-hidden="true" onClick={closeDrawer} />
          <div
            id="mobile-drawer"
            role="dialog"
            aria-modal="true"
            aria-label="Menu"
            className="absolute inset-y-0 left-0 flex w-[82%] max-w-xs flex-col bg-navy px-5 py-5 shadow-pop"
          >
            <div className="flex items-center justify-between">
              <Brand />
              <button
                ref={closeButtonRef}
                type="button"
                onClick={closeDrawer}
                aria-label="Close menu"
                className="focus-ring flex h-10 w-10 items-center justify-center rounded-xl text-white hover:bg-white/10 focus-visible:ring-offset-navy"
              >
                <X className="h-5 w-5" aria-hidden="true" />
              </button>
            </div>
            <div className="mt-8 flex-1">
              <NavLinks onNavigate={() => setDrawerOpen(false)} />
            </div>
            <div className="border-t border-white/10 pt-4">
              <FreshnessIndicator variant="sidebar" />
            </div>
          </div>
        </div>
      )}

      <main id="main" className="mx-auto max-w-7xl px-4 pb-16 pt-6 sm:px-6 lg:px-10 lg:pt-10">
        <FreshnessIndicator variant="banner" />
        <Outlet />
      </main>
    </div>
  );
}
