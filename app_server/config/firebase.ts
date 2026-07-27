import { initializeApp, cert, getApps } from "firebase-admin/app";
import { getFirestore } from "firebase-admin/firestore";
import path from "path";
import fs from "fs";
import { config } from "./environment";

if (getApps().length === 0) {
  const serviceAccountPath = path.isAbsolute(config.firebaseCredentialsPath)
    ? config.firebaseCredentialsPath
    : path.resolve(__dirname, "../..", config.firebaseCredentialsPath);

  if (fs.existsSync(serviceAccountPath)) {
    const serviceAccount = JSON.parse(fs.readFileSync(serviceAccountPath, "utf8"));
    initializeApp({
      credential: cert(serviceAccount),
    });
    console.log(`[Firebase] Initialized with credentials at: ${serviceAccountPath}`);
  } else {
    initializeApp();
    console.warn(`[Firebase] Service account file missing at ${serviceAccountPath}. Using default credentials.`);
  }
}

export const db = getFirestore();
