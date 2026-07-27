import express, { Request, Response } from "express";
import cors from "cors";
import helmet from "helmet";
import { config, validateEnv } from "./config/environment";
import "./config/firebase"; // Triggers Firebase initialization
import authRoutes from "./routes/authRoutes";
import telemetryRoutes from "./routes/telemetryRoutes";

validateEnv();

const app = express();

// Middlewares
app.use(helmet());
app.use(cors());
app.use(express.json());

// Mount Routes
app.use("/auth", authRoutes);
app.use("/telemetry", telemetryRoutes);

// Health Check Route
app.get("/ping", (_req: Request, res: Response) => {
  res.status(200).json({
    status: "ok",
    message: "InstaVault App Server is online and operational!",
    timestamp: new Date().toISOString(),
  });
});

const PORT = config.port;

app.listen(PORT, () => {
  console.log(`🚀 [Server] InstaVault App Server listening on port ${PORT}`);
});

export default app;
