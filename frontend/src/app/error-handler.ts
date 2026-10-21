/**
 * Global error reporting.
 *
 * The previous implementation silenced `console.error` for a broad list of
 * patterns, including the most common runtime error in a React application.
 * That made the whole error-reporting surface of the app non-functional:
 * real API failures and component crashes were silently dropped.
 *
 * Errors are now reported to the console and forwarded to the
 * `/api/v1/monitoring/client-errors` endpoint (best-effort, never blocking,
 * never throwing). Monitoring is opt-in via `NEXT_PUBLIC_ERROR_REPORTING=1`
 * so no user data leaves the browser unless it is explicitly enabled.
 */

const REPORTING_ENDPOINT = "/api/v1/monitoring/client-errors";

function isReportingEnabled(): boolean {
  if (typeof window === "undefined") return false;
  return process.env.NEXT_PUBLIC_ERROR_REPORTING === "1";
}

function reportToBackend(payload: Record<string, unknown>): void {
  if (!isReportingEnabled()) return;

  try {
    void fetch(REPORTING_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      keepalive: true,
    }).catch(() => {
      /* reporting is best-effort and must never surface its own errors */
    });
  } catch {
    /* ignore */
  }
}

if (typeof window !== "undefined") {
  window.addEventListener(
    "error",
    (event) => {
      reportToBackend({
        type: "error",
        message: event.message,
        source: event.filename,
        line: event.lineno,
        column: event.colno,
        stack: event.error instanceof Error ? event.error.stack : undefined,
        timestamp: new Date().toISOString(),
      });
    },
    true
  );

  window.addEventListener("unhandledrejection", (event) => {
    const reason = event.reason;
    reportToBackend({
      type: "unhandledrejection",
      message: reason instanceof Error ? reason.message : String(reason),
      stack: reason instanceof Error ? reason.stack : undefined,
      timestamp: new Date().toISOString(),
    });
  });
}

export {};
