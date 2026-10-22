/**
 * Access-token registry.
 *
 * `api.ts` needs the current access token to set the Authorization header,
 * and `lib/auth` needs the `api` instance to call the auth endpoints. A
 * direct import between the two creates a circular dependency, so the token is
 * published here instead: `lib/auth` writes it, `api.ts` reads it.
 */

let accessToken: string | null = null;

export const setAccessToken = (token: string | null): void => {
  accessToken = token;
};

export const getRegisteredAccessToken = (): string | null => accessToken;
