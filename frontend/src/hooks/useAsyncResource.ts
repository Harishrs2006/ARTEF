"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";

interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

interface UseAsyncResourceOptions {
  /** Poll interval in milliseconds. Set to 0 to disable polling. */
  pollIntervalMs?: number;
  /** Skip the request entirely (e.g. while unauthenticated). */
  enabled?: boolean;
  /** Extract a human-readable message from a rejection. */
  formatError?: (error: unknown) => string;
}

/**
 * Run an async loader with:
 *  - request cancellation on unmount and on re-run (no stale writes),
 *  - a generation guard so a slow response can never overwrite a newer one,
 *  - optional polling that never overlaps with an in-flight request,
 *  - explicit loading / error / empty state.
 */
export function useAsyncResource<T>(
  loader: (signal: AbortSignal) => Promise<T>,
  deps: unknown[],
  options: UseAsyncResourceOptions = {}
): AsyncState<T> & { refresh: () => Promise<void> } {
  const { pollIntervalMs = 0, enabled = true, formatError } = options;

  const [state, setState] = useState<AsyncState<T>>({
    data: null,
    loading: enabled,
    error: null,
  });

  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  const abortRef = useRef<AbortController | null>(null);
  const generationRef = useRef(0);
  const inFlightRef = useRef(false);
  const mountedRef = useRef(true);

  const defaultFormatError = useCallback((error: unknown) => {
    if (axios.isAxiosError(error)) {
      if (error.code === "ERR_CANCELED") return "Request cancelled";
      if (error.code === "ECONNABORTED" || error.code === "ETIMEDOUT") {
        return "The request timed out. Please try again.";
      }
      const data = error.response?.data;
      if (typeof data?.detail === "string") return data.detail;
      if (typeof data?.detail?.message === "string") return data.detail.message;
      if (typeof data?.message === "string") return data.message;
      if (!error.response) {
        return "Unable to reach the ARTEF API. Check that the backend is running.";
      }
    }
    return error instanceof Error ? error.message : "An unexpected error occurred";
  }, []);

  const run = useCallback(async () => {
    if (!enabled) return;

    // Cancel any previous request so a slow response cannot arrive late.
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    const generation = ++generationRef.current;
    inFlightRef.current = true;
    setState((prev) => ({ ...prev, loading: true, error: null }));

    try {
      const data = await loaderRef.current(controller.signal);
      if (!mountedRef.current || generation !== generationRef.current) return;
      setState({ data, loading: false, error: null });
    } catch (error) {
      if (!mountedRef.current || generation !== generationRef.current) return;
      if (axios.isAxiosError(error) && error.code === "ERR_CANCELED") {
        setState((prev) => ({ ...prev, loading: false }));
        return;
      }
      setState({
        data: null,
        loading: false,
        error: (formatError ?? defaultFormatError)(error),
      });
    } finally {
      if (generation === generationRef.current) {
        inFlightRef.current = false;
      }
    }
  }, [enabled, formatError, defaultFormatError]);

  useEffect(() => {
    mountedRef.current = true;
    if (enabled) {
      void run();
    }
    return () => {
      mountedRef.current = false;
      abortRef.current?.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, run, ...deps]);

  useEffect(() => {
    if (!enabled || pollIntervalMs <= 0) return;
    const interval = setInterval(() => {
      // Never overlap with an in-flight request.
      if (!inFlightRef.current && document.visibilityState === "visible") {
        void run();
      }
    }, pollIntervalMs);
    return () => clearInterval(interval);
  }, [enabled, pollIntervalMs, run]);

  return { ...state, refresh: run };
}
