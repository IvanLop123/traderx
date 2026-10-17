// Share only concurrent board reads. Never cache responses or executable quotes.
const boardReads=new Map<string,Promise<any>>();
export function api(path:string,body?:unknown,method="POST"):Promise<any>{
  if(body!==undefined||path!=="/product/cockpit")return request(path,body,method);
  const pending=boardReads.get(path);if(pending)return pending;
  const work=request(path).finally(()=>boardReads.delete(path));boardReads.set(path,work);return work;
}
async function request(path: string, body?: unknown, method = "POST") {
  const response = await fetch(
    "/api/v1" + path,
    body === undefined
      ? { cache: "no-store" }
      : {
          method,
          headers: {
            "Content-Type": "application/json",
            "X-TraderX-Client": "local-ui",
          },
          body: JSON.stringify(body),
        },
  );
  if (!response.headers.get("content-type")?.includes("application/json"))
    throw new Error(
      "TraderX is starting or its backend is unavailable. Keep the launch window open and try again shortly.",
    );
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : JSON.stringify(data.detail ?? data),
    );
  return data;
}
export const money = (v: unknown) =>
  typeof v === "number"
    ? new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: 2,
      }).format(v)
    : "—";
export const number = (v: unknown, d = 2) =>
  typeof v === "number"
    ? v.toLocaleString("en-US", { maximumFractionDigits: d })
    : "—";
export const pct = (v: unknown) =>
  typeof v === "number" ? (v * 100).toFixed(2) + "%" : "—";
export const date = (v: unknown) =>
  typeof v === "string" ? new Date(v).toLocaleString() : "—";
