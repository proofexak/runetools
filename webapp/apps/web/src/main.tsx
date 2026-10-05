import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router";
import { AuthGate } from "@/auth";
import { Layout } from "@/components/layout";
import { ApiError } from "@/lib/api";
import { initTheme } from "@/lib/theme";
import "./index.css";

initTheme();

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: (count, err) => !(err instanceof ApiError && err.status < 500) && count < 2,
    },
  },
});

const router = createBrowserRouter([
  {
    element: <Layout />,
    // pages load on first visit: the chart library only comes with the dashboard
    children: [
      { index: true, lazy: async () => ({ Component: (await import("@/pages/dashboard")).DashboardPage }) },
      { path: "sessions", lazy: async () => ({ Component: (await import("@/pages/sessions")).SessionsPage }) },
      { path: "sessions/:id", lazy: async () => ({ Component: (await import("@/pages/session-detail")).SessionDetailPage }) },
      { path: "bots", lazy: async () => ({ Component: (await import("@/pages/bots")).BotStatsPage }) },
      { path: "accounts", lazy: async () => ({ Component: (await import("@/pages/accounts")).AccountsPage }) },
      { path: "accounts/:id", lazy: async () => ({ Component: (await import("@/pages/account-detail")).AccountDetailPage }) },
      { path: "settings", lazy: async () => ({ Component: (await import("@/pages/settings")).SettingsPage }) },
      { path: "*", lazy: async () => ({ Component: (await import("@/pages/not-found")).NotFoundPage }) },
    ],
  },
]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthGate>
        <RouterProvider router={router} />
      </AuthGate>
    </QueryClientProvider>
  </StrictMode>,
);
