import { EvalsClient } from "./EvalsClient";

export const metadata = { title: "Evaluations · WHO Infodemic Monitor" };

// Admin only: enforced by the middleware (lib/auth/roles.ts, /admin prefix) and by the API (403).
export default function AdminEvalsPage() {
  return <EvalsClient />;
}
