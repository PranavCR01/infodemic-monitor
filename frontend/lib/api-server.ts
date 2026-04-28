import { getServerClient } from "./supabase-server";

const API_URL = process.env.NEXT_PUBLIC_API_URL!;

export async function serverApiFetch(
  path: string,
  options: RequestInit = {}
): Promise<Response> {
  const supabase = getServerClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };

  if (session?.access_token) {
    headers["Authorization"] = `Bearer ${session.access_token}`;
  }

  return fetch(`${API_URL}${path}`, { ...options, headers });
}
