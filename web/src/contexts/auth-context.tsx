"use client";

/**
 * React context for Firebase Authentication state.
 *
 * Provides:
 * - user: current Firebase User or null
 * - loading: true while auth state is being determined
 * - signInWithGoogle: trigger Google Sign-In popup
 * - signOut: sign out the current user
 * - getIdToken: get the current user's ID token for API calls
 */

import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from "react";
import {
  GoogleAuthProvider,
  onAuthStateChanged,
  signInWithPopup,
  signOut as firebaseSignOut,
  type User,
} from "firebase/auth";
import { auth } from "@/lib/firebase";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  signInWithGoogle: () => Promise<void>;
  signOut: () => Promise<void>;
  getIdToken: () => Promise<string | null>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

const googleProvider = new GoogleAuthProvider();

// Dev-mode bypass: when NEXT_PUBLIC_DEV_BYPASS_AUTH=true the provider
// skips Firebase entirely, populates `user` with a stub, and returns
// "dev-user" from getIdToken so the api-client's header check passes.
// The backend's DevUserMiddleware (FIREBASE_AUTH_ENABLED=false) ignores
// the Authorization header and pins user_id to GCLAW_USER_ID
// ("default_user" by default), so any non-empty token works.
const DEV_BYPASS_AUTH =
  process.env.NEXT_PUBLIC_DEV_BYPASS_AUTH === "true";

const DEV_STUB_USER = {
  uid: "dev-user",
  email: "dev@gclaw.local",
  displayName: "Dev User",
  getIdToken: async () => "dev-user",
} as unknown as User;

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(
    DEV_BYPASS_AUTH ? DEV_STUB_USER : null
  );
  const [loading, setLoading] = useState(!DEV_BYPASS_AUTH);

  useEffect(() => {
    if (DEV_BYPASS_AUTH) {
      return;
    }
    const unsubscribe = onAuthStateChanged(auth, (firebaseUser) => {
      setUser(firebaseUser);
      setLoading(false);
    });
    return unsubscribe;
  }, []);

  const signInWithGoogle = useCallback(async () => {
    if (DEV_BYPASS_AUTH) return;
    await signInWithPopup(auth, googleProvider);
  }, []);

  const handleSignOut = useCallback(async () => {
    if (DEV_BYPASS_AUTH) return;
    await firebaseSignOut(auth);
    setUser(null);
  }, []);

  const getIdToken = useCallback(async (): Promise<string | null> => {
    if (DEV_BYPASS_AUTH) return "dev-user";
    if (!user) return null;
    return user.getIdToken();
  }, [user]);

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        signInWithGoogle,
        signOut: handleSignOut,
        getIdToken,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
