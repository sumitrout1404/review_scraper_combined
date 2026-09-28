import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useEffect } from 'react';
import { createBrowserRouter, RouterProvider, useLocation } from 'react-router-dom';
import { ApiError } from './api/client';
import { AppShell } from './components/layout/AppShell';
import { NAV_ITEMS } from './components/layout/navigation';
import { DataHealthPage } from './pages/DataHealthPage';
import { NotFoundPage } from './pages/NotFoundPage';
import { OverviewPage } from './pages/OverviewPage';
import { ReviewsPage } from './pages/ReviewsPage';
import { TopicsPage } from './pages/TopicsPage';

const MAX_RETRIES = 2;

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      refetchOnWindowFocus: false,
      // Client errors (4xx) will not fix themselves, so only retry network, timeout and 5xx errors.
      retry: (failureCount, error) => !(error instanceof ApiError && error.isClientError) && failureCount < MAX_RETRIES,
      retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 8000),
    },
  },
});

/** Keeps the browser tab title in step with the current page. */
function DocumentTitle() {
  const { pathname } = useLocation();
  useEffect(() => {
    const page = NAV_ITEMS.find((item) => item.to === pathname)?.label;
    document.title = page ? `${page} · Azzurro Review Insights` : 'Azzurro Review Insights';
  }, [pathname]);
  return null;
}

function Root() {
  return (
    <>
      <DocumentTitle />
      <AppShell />
    </>
  );
}

const router = createBrowserRouter([
  {
    path: '/',
    element: <Root />,
    children: [
      { index: true, element: <OverviewPage /> },
      { path: 'reviews', element: <ReviewsPage /> },
      { path: 'topics', element: <TopicsPage /> },
      { path: 'data-health', element: <DataHealthPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]);

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}
