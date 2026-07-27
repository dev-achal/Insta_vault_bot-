import { Request, Response, NextFunction } from "express";
import { validateSession } from "../services/sessionService";

// Extend Express Request interface to include authenticated vaultId
export interface AuthenticatedRequest extends Request {
  vaultId?: string;
}

/**
 * Auth Middleware — Protected Route Guard
 *
 * Verifies that incoming requests contain valid authentication headers:
 *   - Authorization: Bearer <session_token>
 *   - X-Vault-ID: <vault_id>
 *
 * Validates the session_token against Firestore using validateSession().
 *
 * If valid: Attaches normalized vaultId to req and calls next().
 * If invalid or missing: Rejects with 401 Unauthorized (forces App re-login).
 */
export const authenticateSession = async (
  req: AuthenticatedRequest,
  res: Response,
  next: NextFunction
): Promise<void> => {
  try {
    const authHeader = req.headers.authorization;
    const vaultIdHeader = req.headers["x-vault-id"] as string | undefined;

    // 1. Check if headers exist
    if (!authHeader || !authHeader.startsWith("Bearer ")) {
      res.status(401).json({
        error: "Unauthorized",
        message: "Missing or invalid Authorization header. Expected format: 'Bearer <session_token>'",
      });
      return;
    }

    if (!vaultIdHeader || typeof vaultIdHeader !== "string") {
      res.status(401).json({
        error: "Unauthorized",
        message: "Missing or invalid X-Vault-ID header.",
      });
      return;
    }

    // Extract raw session token
    const sessionToken = authHeader.split(" ")[1];

    // Normalize Vault ID (ensure VLT- prefix)
    const normalizedVaultId = vaultIdHeader.toUpperCase().startsWith("VLT-")
      ? vaultIdHeader.toUpperCase()
      : `VLT-${vaultIdHeader}`;

    // 2. Validate token against Firestore using sessionService
    const isValid = await validateSession(normalizedVaultId, sessionToken);

    if (!isValid) {
      console.warn(`[AuthMiddleware] Rejected request for ${normalizedVaultId} — Invalid or expired session token.`);
      res.status(401).json({
        error: "Unauthorized",
        message: "Invalid or expired session token. Please re-login.",
      });
      return;
    }

    // 3. Attach vaultId to request for downstream controllers to use
    req.vaultId = normalizedVaultId;

    // Continue to controller
    next();

  } catch (error) {
    console.error("[AuthMiddleware] Error validating session:", error);
    res.status(500).json({ error: "Internal server error during authentication check." });
  }
};
