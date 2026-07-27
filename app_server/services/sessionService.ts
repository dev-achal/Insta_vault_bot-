import { v4 as uuidv4 } from "uuid";
import { db } from "../config/firebase";
import { FieldValue } from "firebase-admin/firestore";

/**
 * Session Service
 *
 * Handles secure session token generation and Firestore persistence.
 * Only ONE active session per user at a time — new login invalidates old session.
 */

/**
 * Creates a new session for a user identified by their Vault ID.
 *
 * Flow:
 *   1. Query Firestore to find the user document by vault_id field.
 *   2. Generate a high-entropy UUID v4 session token.
 *   3. Update ONLY session-related fields on the existing document (safe — bot data untouched).
 *   4. Return the generated session token.
 *
 * @param vaultId - The user's Vault ID (e.g., "VLT-12345")
 * @returns The generated session token string
 * @throws Error if user document is not found
 */
export const createSession = async (vaultId: string): Promise<string> => {
  // Find the user document by vault_id field
  const usersRef = db.collection("users");
  const snapshot = await usersRef.where("vault_id", "==", vaultId).limit(1).get();

  if (snapshot.empty) {
    throw new Error(`User not found for vault_id: ${vaultId}`);
  }

  // Get the document reference (document ID = Telegram user_id)
  const userDoc = snapshot.docs[0];
  const userRef = userDoc.ref;

  // Generate secure session token
  const sessionToken = uuidv4();

  // Update ONLY session fields — .update() is safe, it won't overwrite existing bot fields
  await userRef.update({
    current_session_token: sessionToken,
    last_app_login: FieldValue.serverTimestamp(),
  });

  console.log(`[Session] New session created for ${vaultId}`);

  return sessionToken;
};

/**
 * Validates a session token against Firestore.
 * Used by auth middleware for protecting future API routes.
 *
 * @param vaultId - The user's Vault ID
 * @param sessionToken - The session token to validate
 * @returns true if token matches, false otherwise
 */
export const validateSession = async (vaultId: string, sessionToken: string): Promise<boolean> => {
  const usersRef = db.collection("users");
  const snapshot = await usersRef.where("vault_id", "==", vaultId).limit(1).get();

  if (snapshot.empty) {
    return false;
  }

  const userData = snapshot.docs[0].data();
  return userData.current_session_token === sessionToken;
};
