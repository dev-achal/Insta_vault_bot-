import { Router } from "express";
import { logSessionTelemetry } from "../controllers/telemetryController";
import { authenticateSession } from "../middlewares/authMiddleware";
import { apiRateLimiter } from "../middlewares/rateLimiter";

const router = Router();

// Protect telemetry endpoints with rate limiter and session authentication
router.use(apiRateLimiter);
router.use(authenticateSession);

/**
 * POST /telemetry/log-session
 * Step 11: Asynchronous Background Telemetry Sync
 */
router.post("/log-session", logSessionTelemetry);

export default router;
