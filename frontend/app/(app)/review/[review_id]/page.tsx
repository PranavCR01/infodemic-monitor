import { WorkspaceClient } from "./WorkspaceClient";

export const metadata = { title: "Review · WHO Infodemic Monitor" };

export default function ReviewPage({ params }: { params: { review_id: string } }) {
  return <WorkspaceClient reviewId={params.review_id} />;
}
