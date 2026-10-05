import { BarChart3, History, LayoutDashboard, LogOut, Monitor, Moon, Settings, Sun, Users } from "lucide-react";
import { NavLink, Outlet } from "react-router";
import { useLogout, useMe } from "@/auth";
import { Button } from "@/components/ui/button";
import { useTheme, type Theme } from "@/lib/theme";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/sessions", label: "Sessions", icon: History },
  { to: "/bots", label: "Bot stats", icon: BarChart3 },
  { to: "/accounts", label: "Accounts", icon: Users },
  { to: "/settings", label: "Settings", icon: Settings },
];

const NEXT_THEME: Record<Theme, Theme> = { system: "light", light: "dark", dark: "system" };
const THEME_ICON = { system: Monitor, light: Sun, dark: Moon };

export function Layout() {
  const me = useMe();
  const logout = useLogout();
  const [theme, setTheme] = useTheme();
  const ThemeIcon = THEME_ICON[theme];

  return (
    <div className="flex min-h-svh flex-col md:flex-row">
      <aside className="bg-sidebar flex shrink-0 flex-col border-b md:sticky md:top-0 md:h-svh md:w-56 md:border-r md:border-b-0">
        <div className="flex items-center gap-2 px-4 py-4">
          <img src="/favicon.svg" alt="" className="size-6" />
          <span className="font-semibold tracking-tight">RuneTools</span>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-2 pb-2 md:flex-col md:pb-0">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) => cn(
                "flex items-center gap-2 rounded-md px-3 py-2 text-sm whitespace-nowrap transition-colors",
                isActive ? "bg-accent text-accent-foreground font-medium" : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
              )}
            >
              <Icon className="size-4" />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto hidden items-center gap-1 border-t px-3 py-3 md:flex">
          <span className="text-muted-foreground truncate text-sm">
            {me.data?.state === "authenticated" ? me.data.username : ""}
          </span>
          <Button variant="ghost" size="icon-sm" className="ml-auto" title={`Theme: ${theme}`} onClick={() => setTheme(NEXT_THEME[theme])}>
            <ThemeIcon />
          </Button>
          <Button variant="ghost" size="icon-sm" title="Log out" onClick={() => logout.mutate()}>
            <LogOut />
          </Button>
        </div>
      </aside>
      <main className="min-w-0 flex-1 p-4 md:p-8">
        <Outlet />
      </main>
    </div>
  );
}

export function PageHeader({ title, description, children }: { title: string; description?: string; children?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="text-muted-foreground mt-1 text-sm">{description}</p>}
      </div>
      {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
    </div>
  );
}
