import { Request, Response } from "express";
import crypto from "crypto";
import { db } from "../config/firebase";
import { verifyPlayIntegrity } from "../services/integrityService";
import { createSession } from "../services/sessionService";

/**
 * Step 1 of Auth Flow — Vault ID Verification
 *
 * Receives { vault_id } from the Android app.
 * Queries Firestore 'users' collection where vault_id field matches.
 * If found → generates a secure nonce and returns it.
 * If not found → returns 404.
 */
export const verifyVaultId = async (req: Request, res: Response): Promise<void> => {
  try {
    const { vault_id } = req.body;

    // Input validation
    if (!vault_id || typeof vault_id !== "string") {
      res.status(400).json({ valid: false, error: "vault_id is required and must be a string." });
      return;
    }

    // Normalize: ensure VLT- prefix
    const normalizedId = vault_id.toUpperCase().startsWith("VLT-")
      ? vault_id.toUpperCase()
      : `VLT-${vault_id}`;

    console.log(`[Auth] Vault ID lookup request: ${normalizedId}`);

    // Query Firestore — bot stores vault_id as a field inside user documents
    const usersRef = db.collection("users");
    const snapshot = await usersRef.where("vault_id", "==", normalizedId).limit(1).get();

    if (snapshot.empty) {
      console.log(`[Auth] Vault ID not found: ${normalizedId}`);
      res.status(404).json({ valid: false, error: "Vault ID not found" });
      return;
    }

    // Vault ID exists — generate a secure one-time nonce (32 bytes, base64url encoded)
    const nonce = crypto.randomBytes(32).toString("base64url");

    console.log(`[Auth] Vault ID verified: ${normalizedId} | Nonce generated`);

    res.status(200).json({
      valid: true,
      nonce: nonce,
    });

  } catch (error) {
    console.error("[Auth] Error in verifyVaultId:", error);
    res.status(500).json({ valid: false, error: "Internal server error" });
  }
};

/**
 * Step 3 of Auth Flow — Integrity Verification & Session Creation
 *
 * Receives { vault_id, integrity_token } from the Android app.
 * 1. Verifies vault_id exists in Firestore
 * 2. Verifies integrity_token via Google Play Integrity API
 * 3. Creates a new session token and saves it to Firestore
 * 4. Returns session_token + user_profile data for the app to cache locally
 */
export const verifyIntegrity = async (req: Request, res: Response): Promise<void> => {
  try {
    const { vault_id, integrity_token } = req.body;

    // Input validation
    if (!vault_id || typeof vault_id !== "string") {
      res.status(400).json({ error: "vault_id is required and must be a string." });
      return;
    }
    if (!integrity_token || typeof integrity_token !== "string") {
      res.status(400).json({ error: "integrity_token is required and must be a string." });
      return;
    }

    // Normalize vault_id
    const normalizedId = vault_id.toUpperCase().startsWith("VLT-")
      ? vault_id.toUpperCase()
      : `VLT-${vault_id}`;

    console.log(`[Auth] Integrity verification request for: ${normalizedId}`);

    // 1. Verify vault_id exists in Firestore
    const usersRef = db.collection("users");
    const snapshot = await usersRef.where("vault_id", "==", normalizedId).limit(1).get();

    if (snapshot.empty) {
      console.log(`[Auth] User not found: ${normalizedId}`);
      res.status(404).json({ error: "User not found" });
      return;
    }

    // 2. Verify Play Integrity token
    try {
      await verifyPlayIntegrity(integrity_token);
    } catch (integrityError: any) {
      console.error(`[Auth] Integrity check failed for ${normalizedId}:`, integrityError.message);
      res.status(403).json({
        error: "Device integrity check failed",
        details: integrityError.message
      });
      return;
    }

    // 3. Create session token and save to Firestore
    const sessionToken = await createSession(normalizedId);

    // 4. Extract user profile data for the app's local cache
    const userData = snapshot.docs[0].data();
    const userProfile = {
      vault_id: userData.vault_id || normalizedId,
      first_name: userData.first_name || "Vault Member",
      spark_balance: userData.spark_balance || 0,
      rank_tier: userData.rank_tier || "Rookie Vaulter",
      lifetime_sparks: userData.lifetime_sparks || 0,
      total_orders: userData.total_orders || 0,
      total_views_recv: userData.total_views_recv || 0,
      instagram_handle: userData.instagram_handle || null,
      referral_count: userData.referral_count || 0,
    };

    console.log(`[Auth] Login successful for ${normalizedId} | Session created`);

    res.status(200).json({
      session_token: sessionToken,
      user_profile: userProfile,
    });

  } catch (error) {
    console.error("[Auth] Error in verifyIntegrity:", error);
    res.status(500).json({ error: "Internal server error" });
  }
};
