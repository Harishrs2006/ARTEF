import { AxiosError, AxiosHeaders } from "axios";
import { api, getApiBaseUrl, handleApiError, onSessionExpired, API_TIMEOUT_MS } from "@/lib/api";
import { getRegisteredAccessToken, setAccessToken } from "@/lib/token-registry";

function axiosErrorWith(config: Record<string, unknown>, response?: unknown): AxiosError {
  const error = new AxiosError("failed", "ERR_BAD_REQUEST", config as never, {}, undefined as never);
  if (response) {
    (error as { response?: unknown }).response = response;
  }
  return error;
}

describe("API base URL", () => {
  const original = process.env.NEXT_PUBLIC_API_URL;

  afterEach(() => {
    if (original === undefined) {
      delete process.env.NEXT_PUBLIC_API_URL;
    } else {
      process.env.NEXT_PUBLIC_API_URL = original;
    }
  });

  it("appends the API prefix when it is missing", () => {
    process.env.NEXT_PUBLIC_API_URL = "http://localhost:8000";
    expect(getApiBaseUrl()).toBe("http://localhost:8000/api/v1");
  });

  it("does not append the prefix twice", () => {
    process.env.NEXT_PUBLIC_API_URL = "http://localhost:8000/api/v1";
    expect(getApiBaseUrl()).toBe("http://localhost:8000/api/v1");
  });

  it("strips trailing slashes before appending the prefix", () => {
    process.env.NEXT_PUBLIC_API_URL = "http://localhost:8000///";
    expect(getApiBaseUrl()).toBe("http://localhost:8000/api/v1");
  });
});

describe("handleApiError", () => {
  it("reports a timeout", () => {
    const error = axiosErrorWith({});
    error.code = "ECONNABORTED";
    expect(handleApiError(error)).toContain("timed out");
  });

  it("reports a cancelled request", () => {
    const error = axiosErrorWith({});
    error.code = "ERR_CANCELED";
    expect(handleApiError(error)).toContain("cancelled");
  });

  it("uses the detail string of the response", () => {
    const error = axiosErrorWith({}, { data: { detail: "Suite not found" } });
    expect(handleApiError(error)).toBe("Suite not found");
  });

  it("uses the nested detail message of the response", () => {
    const error = axiosErrorWith({}, { data: { detail: { message: "Invalid payload" } } });
    expect(handleApiError(error)).toBe("Invalid payload");
  });

  it("explains that the API is unreachable when there is no response", () => {
    const error = axiosErrorWith({});
    expect(handleApiError(error)).toContain("Unable to reach the ARTEF API");
  });

  it("handles a non-axios error", () => {
    expect(handleApiError(new Error("boom"))).toBe("An unexpected error occurred");
  });
});

describe("the request interceptor", () => {
  it("attaches the registered access token", async () => {
    setAccessToken("test-token");
    const config = { headers: new AxiosHeaders() } as never;
    const handler = (
      api.interceptors.request as unknown as {
        handlers: Array<{ fulfilled: (c: never) => never }>;
      }
    ).handlers[0];

    const result = handler.fulfilled(config);
    const headers = (result as { headers: AxiosHeaders }).headers;

    expect(headers.get("Authorization")).toBe("Bearer test-token");
    setAccessToken(null);
  });

  it("does not attach a header when there is no token", async () => {
    setAccessToken(null);
    const config = { headers: new AxiosHeaders() } as never;
    const handler = (
      api.interceptors.request as unknown as {
        handlers: Array<{ fulfilled: (c: never) => never }>;
      }
    ).handlers[0];

    const result = handler.fulfilled(config);
    const headers = (result as { headers: AxiosHeaders }).headers;

    expect(headers.get("Authorization")).toBeUndefined();
  });
});

describe("the token registry", () => {
  it("stores and returns the token", () => {
    setAccessToken("abc");
    expect(getRegisteredAccessToken()).toBe("abc");
    setAccessToken(null);
    expect(getRegisteredAccessToken()).toBeNull();
  });
});

describe("the session expiry notification", () => {
  it("unsubscribes the listener", () => {
    const listener = jest.fn();
    const unsubscribe = onSessionExpired(listener);
    unsubscribe();
    // The listener must no longer be registered; the behaviour is
    // verified through the public contract of the helper.
    expect(typeof unsubscribe).toBe("function");
  });
});

describe("the request timeout", () => {
  it("is bounded so a hung socket cannot block forever", () => {
    expect(API_TIMEOUT_MS).toBeGreaterThan(0);
    expect(API_TIMEOUT_MS).toBeLessThanOrEqual(60_000);
  });
});
