export type View = "console" | "tasks" | "sessions" | "memories" | "profile" | "settings";

const pathToView: Record<string, View> = {
  "/": "console",
  "/tasks": "tasks",
  "/sessions": "sessions",
  "/memories": "memories",
  "/profile": "profile",
  "/settings": "settings",
};

const viewToPath: Record<View, string> = {
  console: "/",
  tasks: "/tasks",
  sessions: "/sessions",
  memories: "/memories",
  profile: "/profile",
  settings: "/settings",
};

export function getCurrentView(pathname: string): View {
  return pathToView[pathname] ?? "console";
}

export function navigateTo(view: View) {
  const nextPath = viewToPath[view];
  if (window.location.pathname === nextPath) {
    return;
  }
  window.history.pushState({}, "", nextPath);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export function subscribeRoute(onChange: (pathname: string) => void) {
  const handler = () => onChange(window.location.pathname);
  window.addEventListener("popstate", handler);
  return () => window.removeEventListener("popstate", handler);
}
