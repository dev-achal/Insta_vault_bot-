import { FieldValue, Timestamp } from "firebase-admin/firestore";
import { db } from "../config/firebase";

const NONCE_TTL_MS = 5 * 60 * 1000;
const ACTIVE_NONCES_COLLECTION = "active_nonces";

export class NonceValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "NonceValidationError";
  }
}

/** Stores a server-issued nonce for one Play Integrity verification attempt. */
export const storeNonce = async (nonce: string, vaultId: string): Promise<void> => {
  const expiresAt = Timestamp.fromMillis(Date.now() + NONCE_TTL_MS);

  await db.collection(ACTIVE_NONCES_COLLECTION).doc(nonce).set({
    nonce,
    vault_id: vaultId,
    created_at: FieldValue.serverTimestamp(),
    expires_at: expiresAt,
  });
};

/**
 * Atomically validates and burns a nonce.
 *
 * The transaction makes a nonce single-use even when replay requests arrive
 * concurrently: after the first transaction deletes it, subsequent attempts
 * observe a missing nonce and fail.
 */
export const consumeNonce = async (nonce: string, vaultId: string): Promise<void> => {
  if (!nonce) {
    throw new NonceValidationError("Integrity token did not contain a nonce.");
  }

  const nonceRef = db.collection(ACTIVE_NONCES_COLLECTION).doc(nonce);

  const result = await db.runTransaction(async (transaction) => {
    const nonceSnapshot = await transaction.get(nonceRef);

    if (!nonceSnapshot.exists) {
      throw new NonceValidationError("Nonce is missing, expired, or was already used.");
    }

    const data = nonceSnapshot.data();
    const expiresAt = data?.expires_at as Timestamp | undefined;

    if (!expiresAt || expiresAt.toMillis() <= Date.now()) {
      transaction.delete(nonceRef);
      return "expired";
    }

    if (data?.vault_id !== vaultId) {
      throw new NonceValidationError("Nonce does not belong to this Vault ID.");
    }

    transaction.delete(nonceRef);
    return "consumed";
  });

  if (result === "expired") {
    throw new NonceValidationError("Nonce has expired.");
  }
};
