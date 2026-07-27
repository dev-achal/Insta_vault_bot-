import rateLimit from "express-rate-limit";

/**
 * Rate Limiting Middlewares — Step 10
 *
 * Production-grade anti-abuse and anti-brute-force protection.
 * Uses express-rate-limit with standard RateLimit headers.
 */

/**
 * Strict Rate Limiter for Authentication Endpoints (/auth/*)
 *
 * Prevents brute-forcing Vault IDs or spamming Play Integrity verification.
 * Limit: 10 requests per 15 minutes per IP address.
 */
export const authRateLimiter = rateLimit({
  windowMs: 15 * 60 * 1000, // 15-minute window
  max: 10, // Limit each IP to 10 requests per windowMs
  standardHeaders: true, // Return rate limit info in `RateLimit-*` headers
  legacyHeaders: false, // Disable `X-RateLimit-*` headers
  message: {
    status: 429,
    error: "Too Many Requests",
    message: "Too many authentication attempts from this IP. Please try again after 15 minutes.",
  },
});

/**
 * General Rate Limiter for Protected API Routes
 *
 * Prevents general API abuse while keeping legitimate app usage smooth.
 * Limit: 100 requests per 15 minutes per IP address.
 */
export const apiRateLimiter = rateLimit({
  windowMs: 15 * 60 * 1000, // 15-minute window
  max: 100, // Limit each IP to 100 requests per windowMs
  standardHeaders: true,
  legacyHeaders: false,
  message: {
    status: 429,
    error: "Too Many Requests",
    message: "Too many requests. Please slow down and try again later.",
  },
});
