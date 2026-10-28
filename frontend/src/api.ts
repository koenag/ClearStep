export async function api<T = any>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch("/api" + path, {
    method,
    headers:
      body instanceof FormData
        ? undefined
        : { "Content-Type": "application/json" },
    body:
      body === undefined
        ? undefined
        : body instanceof FormData
          ? body
          : JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : JSON.stringify(data.detail),
    );
  return data;
}
export type Kind = "supplier_switch" | "promotional_event";
export type Result = {
  net_benefit: number;
  roi: number | null;
  upfront_cash: number;
  horizon: number;
  break_even_month?: number | null;
  break_even_visits?: number | null;
  monthly_savings?: number;
  current_monthly_cost?: number;
  proposed_monthly_cost?: number;
  event_contribution?: number;
  repeat_contribution?: number;
  total_cost?: number;
  timeline: { month: number; cumulative: number; savings: number }[];
};
export type Analysis = {
  decision_type: Kind;
  inputs: Record<string, string | number>;
  summary: string;
  scenarios: {
    name: string;
    inputs: Record<string, string | number>;
    result: Result;
  }[];
  assumptions: {
    name: string;
    value: number;
    unit: string;
    provenance: string;
  }[];
  risks: string[];
  calculation_version: string;
  scenario_note: string;
};
export const usd = (n: number) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(n);
