import { Response } from "express";
import { db } from "../config/firebase";
import { FieldValue } from "firebase-admin/firestore";
import { AuthenticatedRequest } from "../middlewares/authMiddleware";

/**
 * Deep Telemetry Payload Interface
 * Matches all device metrics gathered by the Android app's background worker.
 */
export interface TelemetryPayload {
  device_model?: string;       // e.g., "Galaxy S21 Ultra"
  device_brand?: string;       // e.g., "Samsung"
  os_version?: string;         // e.g., "Android 14 (API 34)"
  app_version?: string;        // e.g., "1.0.0"
  build_number?: number;       // e.g., 101
  device_locale?: string;      // e.g., "en_IN"
  screen_density?: string;     // e.g., "xxhdpi / 480dpi"
  network_type?: string;       // e.g., "WIFI" / "CELLULAR_5G"
  is_emulator?: boolean;       // Client-side detection flag
  is_rooted?: boolean;         // Client-side detection flag
  client_timestamp?: string;   // Local device ISO timestamp
}

/**
 * Step 11 — Async Telemetry Logger Controller
 *
 * Protected Route Controller (requires valid session token via authMiddleware).
 *
 * Dual Writing Strategy:
 *   1. Writes a new document in 'audit_logs' collection for complete historical audit trail.
 *   2. Updates 'app_device_info' map on the existing user document in 'users' collection for fast latest-device lookup.
 *
 * Returns 202 Accepted immediately (fire-and-forget for client performance).
 */
export const logSessionTelemetry = async (
  req: AuthenticatedRequest,
  res: Response
): Promise<void> => {
  try {
    const vaultId = req.vaultId;

    if (!vaultId) {
      res.status(401).json({ error: "Unauthorized", message: "Vault ID missing from request." });
      return;
    }

    const payload: TelemetryPayload = req.body || {};

    // Server-enriched metadata
    const ipAddress =
      (req.headers["x-forwarded-for"] as string)?.split(",")[0].trim() ||
      req.ip ||
      req.socket.remoteAddress ||
      "0.0.0.0";

    const userAgent = req.headers["user-agent"] || "InstaVault-Android-App";

    // Standardized Telemetry Audit Record
    const auditRecord = {
      vault_id: vaultId,
      event_type: "app_session_telemetry",
      device_model: payload.device_model || "Unknown",
      device_brand: payload.device_brand || "Unknown",
      os_version: payload.os_version || "Unknown",
      app_version: payload.app_version || "1.0.0",
      build_number: payload.build_number || 1,
      device_locale: payload.device_locale || "en",
      screen_density: payload.screen_density || "unknown",
      network_type: payload.network_type || "UNKNOWN",
      is_emulator: payload.is_emulator ?? false,
      is_rooted: payload.is_rooted ?? false,
      client_timestamp: payload.client_timestamp || new Date().toISOString(),
      ip_address: ipAddress,
      user_agent: userAgent,
      logged_at: FieldValue.serverTimestamp(),
    };

    console.log(`[Telemetry] Logging background telemetry for ${vaultId} (${auditRecord.device_model}, ${auditRecord.os_version})`);

    // 1. Write historical log document to 'audit_logs' collection
    const auditPromise = db.collection("audit_logs").add(auditRecord);

    // 2. Update latest device info map on user document in 'users' collection
    const usersRef = db.collection("users");
    const userSnapshotPromise = usersRef.where("vault_id", "==", vaultId).limit(1).get();

    // Execute database operations concurrently
    const [, userSnapshot] = await Promise.all([auditPromise, userSnapshotPromise]);

    if (!userSnapshot.empty) {
      const userDocRef = userSnapshot.docs[0].ref;
      await userDocRef.update({
        app_device_info: {
          device_model: auditRecord.device_model,
          device_brand: auditRecord.device_brand,
          os_version: auditRecord.os_version,
          app_version: auditRecord.app_version,
          network_type: auditRecord.network_type,
          is_emulator: auditRecord.is_emulator,
          is_rooted: auditRecord.is_rooted,
          ip_address: auditRecord.ip_address,
          last_telemetry_at: FieldValue.serverTimestamp(),
        },
      });
    }

    // 3. Return 202 Accepted immediately
    res.status(202).json({
      status: "accepted",
      message: "Telemetry logged successfully.",
    });

  } catch (error) {
    console.error("[Telemetry] Error logging telemetry:", error);
    // Even if telemetry logging fails internally, don't crash app flow
    res.status(202).json({
      status: "accepted",
      message: "Telemetry received.",
    });
  }
};
