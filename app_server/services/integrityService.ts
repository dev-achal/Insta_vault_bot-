import { GoogleAuth } from "google-auth-library";
import { config } from "../config/environment";

/**
 * Play Integrity Verification Service
 *
 * Decodes and verifies the encrypted integrity token sent by the Android app.
 * Uses Google's playintegrity.googleapis.com API via service account credentials.
 *
 * In development mode (NODE_ENV=development), returns a mock successful verdict
 * since real tokens can only come from actual Android devices.
 */

// The verdict structure returned after decoding the integrity token
export interface IntegrityVerdict {
  requestDetails: {
    nonce: string;
    requestPackageName: string;
    timestampMillis: string;
  };
  appIntegrity: {
    appRecognitionVerdict: string; // "PLAY_RECOGNIZED" | "UNRECOGNIZED_VERSION" | "UNEVALUATED"
  };
  deviceIntegrity: {
    deviceRecognitionVerdict: string[]; // ["MEETS_DEVICE_INTEGRITY"] etc.
  };
  accountDetails: {
    appLicensingVerdict: string; // "LICENSED" | "UNLICENSED" | "UNEVALUATED"
  };
}

/**
 * Verifies a Play Integrity token by calling Google's decodeIntegrityToken API.
 *
 * @param integrityToken - The encrypted JWT token from PlayIntegrityManager on Android
 * @returns IntegrityVerdict containing device, app, and account integrity results
 * @throws Error if verification fails or verdict is unacceptable
 */
export const verifyPlayIntegrity = async (integrityToken: string): Promise<IntegrityVerdict> => {

  // ──────────────────────────────────────────────────────────────
  // DEV BYPASS: Return mock verdict in development environment
  // Real Play Integrity tokens can ONLY come from actual Android devices.
  // ──────────────────────────────────────────────────────────────
  if (config.nodeEnv === "development") {
    console.log("[Integrity] DEV MODE — Returning mock successful verdict.");
    return {
      requestDetails: {
        nonce: "dev-mock-nonce",
        requestPackageName: "com.instavault.app",
        timestampMillis: Date.now().toString(),
      },
      appIntegrity: {
        appRecognitionVerdict: "PLAY_RECOGNIZED",
      },
      deviceIntegrity: {
        deviceRecognitionVerdict: ["MEETS_DEVICE_INTEGRITY"],
      },
      accountDetails: {
        appLicensingVerdict: "LICENSED",
      },
    };
  }

  // ──────────────────────────────────────────────────────────────
  // PRODUCTION: Real Google Play Integrity API call
  // ──────────────────────────────────────────────────────────────
  const projectNumber = config.gcpProjectNumber;
  const packageName = "com.instavault.app";

  // Authenticate using service account credentials (auto-detected from GOOGLE_APPLICATION_CREDENTIALS
  // or the firebase_credentials.json we already loaded)
  const auth = new GoogleAuth({
    scopes: ["https://www.googleapis.com/auth/playintegrity"],
  });

  const client = await auth.getClient();

  // Call Google's decodeIntegrityToken endpoint
  const url = `https://playintegrity.googleapis.com/v1/${packageName}:decodeIntegrityToken`;

  const response = await client.request<{ tokenPayloadExternal: IntegrityVerdict }>({
    url,
    method: "POST",
    data: {
      integrity_token: integrityToken,
    },
  });

  const verdict = response.data.tokenPayloadExternal;

  if (!verdict) {
    throw new Error("Empty verdict received from Google Play Integrity API.");
  }

  // Validate critical integrity signals
  const deviceVerdicts = verdict.deviceIntegrity?.deviceRecognitionVerdict || [];

  if (!deviceVerdicts.includes("MEETS_DEVICE_INTEGRITY")) {
    throw new Error(
      `Device integrity check failed. Verdicts: [${deviceVerdicts.join(", ")}]`
    );
  }

  console.log(`[Integrity] Token verified successfully. Device verdicts: [${deviceVerdicts.join(", ")}]`);

  return verdict;
};
