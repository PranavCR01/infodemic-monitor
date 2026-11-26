import { DashboardClient } from "./DashboardClient";

export const metadata = { title: "Dashboard · WHO Infodemic Monitor" };

// Any signed-in role (the middleware sends signed-out users to sign in; the API answers 401).
export default function DashboardPage() {
  return <DashboardClient />;
}
