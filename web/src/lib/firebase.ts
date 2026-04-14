/**
 * Firebase client initialization.
 *
 * Reads config from NEXT_PUBLIC_FIREBASE_* environment variables.
 * Initializes Firebase App, Auth, and Firestore instances.
 */

import { initializeApp, getApps, type FirebaseApp } from "firebase/app";
import { getAuth, type Auth } from "firebase/auth";
import { getFirestore, type Firestore } from "firebase/firestore";

const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY || "",
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN || "",
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID || "",
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET || "",
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID || "",
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID || "",
};

// When NEXT_PUBLIC_DEV_BYPASS_AUTH=true Firebase is unused — the
// auth-context returns a stub user without ever touching Firebase.
// But the module is still imported at build time (next build
// prerenders pages that transitively import this file), so we must
// not call initializeApp with an empty apiKey or Firebase throws
// auth/invalid-api-key and the build fails.
const hasFirebaseConfig = !!firebaseConfig.apiKey;

let app: FirebaseApp;
if (hasFirebaseConfig) {
  if (getApps().length === 0) {
    app = initializeApp(firebaseConfig);
  } else {
    app = getApps()[0];
  }
} else {
  // Placeholder — Firebase calls will fail at runtime, but
  // auth-context's DEV_BYPASS_AUTH path never calls them.
  app = {} as FirebaseApp;
}

export const firebaseApp: FirebaseApp = app;
export const auth: Auth = hasFirebaseConfig ? getAuth(app) : ({} as Auth);
export const db: Firestore = hasFirebaseConfig
  ? getFirestore(app)
  : ({} as Firestore);

/** True when real Firebase config is available (auth + Firestore). */
export const firebaseConfigured = hasFirebaseConfig;
