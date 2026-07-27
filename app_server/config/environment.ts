import path from "path";
import dotenv from "dotenv";

// Load .env from one directory up (bot project root)
const envPath = path.resolve(__dirname, "../../.env");
dotenv.config({ path: envPath });

export const config = {
  port: parseInt(process.env.APP_SERVER_PORT || process.env.PORT || "3000", 10),
  firebaseCredentialsPath: process.env.FIREBASE_CREDENTIALS_PATH || path.resolve(__dirname, "../../firebase_credentials.json"),
  gcpProjectNumber: process.env.GCP_PROJECT_NUMBER || "1040039421212",
  nodeEnv: process.env.NODE_ENV || "development",
};

export const validateEnv = (): void => {
  console.log(`[Config] Environment loaded from: ${envPath}`);
  console.log(`[Config] Server running in '${config.nodeEnv}' mode on port ${config.port}`);
};
