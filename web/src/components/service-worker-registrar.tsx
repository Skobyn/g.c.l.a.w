"use client";

/**
 * ServiceWorkerRegistrar
 * Registers the service worker (public/sw.js) once on client mount.
 * Renders nothing — purely a side-effect component.
 */

import { useEffect } from "react";

export function ServiceWorkerRegistrar() {
  useEffect(() => {
    if (
      typeof window !== "undefined" &&
      "serviceWorker" in navigator
    ) {
      navigator.serviceWorker
        .register("/sw.js")
        .then((registration) => {
          console.log("[SW] Registered, scope:", registration.scope);
        })
        .catch((err) => {
          console.warn("[SW] Registration failed:", err);
        });
    }
  }, []);

  return null;
}
