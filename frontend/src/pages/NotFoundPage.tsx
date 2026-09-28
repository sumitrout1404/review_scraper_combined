import { Compass } from 'lucide-react';
import { Link } from 'react-router-dom';
import { buttonClasses } from '../components/ui/buttonStyles';
import { EmptyState } from '../components/ui/States';

export function NotFoundPage() {
  return (
    <div className="card mt-10">
      <EmptyState
        icon={<Compass className="h-5 w-5" aria-hidden="true" />}
        title="Page not found"
        message="The page you were looking for doesn’t exist. It may have moved."
        action={
          <Link to="/" className={buttonClasses('primary', 'sm')}>
            Go to the overview
          </Link>
        }
      />
    </div>
  );
}
