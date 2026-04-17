import { useEffect, useState } from "react";

import { AppShell } from "./components/AppShell";
import { ConsolePage } from "./pages/ConsolePage";
import { MemoriesPage } from "./pages/MemoriesPage";
import { ProfilePage } from "./pages/ProfilePage";
import { SessionsPage } from "./pages/SessionsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { TasksPage } from "./pages/TasksPage";
import { getCurrentView, navigateTo, subscribeRoute, type View } from "./routing";

export function NewApp() {
  const [view, setView] = useState<View>(() => getCurrentView(window.location.pathname));

  useEffect(() => subscribeRoute((pathname) => setView(getCurrentView(pathname))), []);

  return (
    <AppShell currentView={view} onNavigate={navigateTo}>
      {view === "console" ? <ConsolePage /> : null}
      {view === "tasks" ? <TasksPage /> : null}
      {view === "sessions" ? <SessionsPage /> : null}
      {view === "memories" ? <MemoriesPage /> : null}
      {view === "profile" ? <ProfilePage /> : null}
      {view === "settings" ? <SettingsPage /> : null}
    </AppShell>
  );
}
