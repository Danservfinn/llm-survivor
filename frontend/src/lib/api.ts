"use client";

function defaultApiBase() {
  if (typeof window === "undefined") {
    return "";
  }
  const isLocalHost = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
  const isNextDevPort = window.location.port === "3000" || window.location.port === "3001";
  return isLocalHost && isNextDevPort
    ? "http://localhost:8000"
    : "";
}

export function apiUrl(path: string) {
  const configuredBase = process.env.NEXT_PUBLIC_API_URL;
  const base = configuredBase ?? defaultApiBase();
  return `${base}${path}`;
}

export function mediaUrl(path: string) {
  if (path.startsWith("http")) {
    return path;
  }
  return apiUrl(path);
}
