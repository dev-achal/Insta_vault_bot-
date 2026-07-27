import { Router, Response } from "express";
import { verifyVaultId, verifyIntegrity } from "../controllers/authController";
import { authenticateSession, AuthenticatedRequest } from "../middlewares/authMiddleware";
import { authRateLimiter } from "../middlewares/rateLimiter";

const router = Router();

// Apply strict rate limiting to all authentication routes (Step 10)
router.use(authRateLimiter);

/**
 * POST /auth/verify-vault-id
 * Step 1: Vault ID lookup against Firestore + nonce generation
 */
router.post("/verify-vault-id", verifyVaultId);

/**
 * POST /auth/verify-integrity
 * Step 3: Play Integrity verification + session creation + user profile return
 */
router.post("/verify-integrity", verifyIntegrity);

/**
 * GET /auth/me
 * Protected Route Example — Protected by authenticateSession middleware (Step 9)
 */
router.get("/me", authenticateSession, (req: AuthenticatedRequest, res: Response) => {
  res.status(200).json({
    status: "success",
    message: "Access granted — Session token is valid!",
    authenticated_vault_id: req.vaultId,
  });
});

export default router;
