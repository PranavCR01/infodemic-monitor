import { QueueClient } from "./QueueClient";

export const metadata = { title: "Review queue · WHO Infodemic Monitor" };

// Reviewer and admin only: enforced by the middleware (lib/auth/roles.ts) and the API.
export default function ReviewQueuePage() {
  return <QueueClient />;
}
