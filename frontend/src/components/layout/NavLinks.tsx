import clsx from 'clsx';
import { NavLink, useSearchParams } from 'react-router-dom';
import { pickGlobal } from '../../lib/urlParams';
import { NAV_ITEMS } from './navigation';

/** Sidebar/drawer navigation. Keeps the property and date filters when switching pages. */
export function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const [params] = useSearchParams();
  const search = pickGlobal(params).toString();

  return (
    <nav aria-label="Main">
      <ul className="space-y-1">
        {NAV_ITEMS.map(({ to, label, description, icon: Icon }) => (
          <li key={to}>
            <NavLink
              to={{ pathname: to, search }}
              end={to === '/'}
              onClick={onNavigate}
              className={({ isActive }) =>
                clsx(
                  'focus-ring group flex items-start gap-3 rounded-xl px-3 py-2.5 transition-colors focus-visible:ring-offset-navy',
                  isActive ? 'bg-white/10 text-white' : 'text-sand/80 hover:bg-white/5 hover:text-white',
                )
              }
            >
              {({ isActive }) => (
                <>
                  <Icon
                    className={clsx('mt-0.5 h-5 w-5 shrink-0', isActive ? 'text-coral' : 'text-sand/60 group-hover:text-sand')}
                    aria-hidden="true"
                  />
                  <span>
                    <span className="block text-sm font-medium">{label}</span>
                    <span className="block text-xs text-sand/60">{description}</span>
                  </span>
                </>
              )}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
