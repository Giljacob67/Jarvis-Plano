import * as http from "http";
import express, { type Express, type Request, type Response, type NextFunction } from "express";
import cors from "cors";
import router from "./routes";

const JARVIS_HOST = "127.0.0.1";
const JARVIS_PORT = 8000;

function proxyToJarvis(req: Request, res: Response, jarvisPath: string): void {
  const options: http.RequestOptions = {
    hostname: JARVIS_HOST,
    port: JARVIS_PORT,
    path: jarvisPath,
    method: req.method,
    headers: { ...req.headers, host: `${JARVIS_HOST}:${JARVIS_PORT}` },
  };

  const proxyReq = http.request(options, (proxyRes) => {
    res.writeHead(proxyRes.statusCode ?? 502, proxyRes.headers);
    proxyRes.pipe(res);
  });

  proxyReq.on("error", (err) => {
    console.error("Jarvis proxy error:", err.message);
    if (!res.headersSent) {
      res.status(502).json({ error: "Jarvis unavailable" });
    }
  });

  req.pipe(proxyReq);
}

const app: Express = express();

app.use(cors());

// ── Jarvis proxy routes ───────────────────────────────────────────────────────
// MUST come before body parsers so the raw body stream is available for piping.
// The /api prefix is stripped before forwarding to Jarvis Python (port 8000):
//   POST /api/webhooks/telegram  →  POST /webhooks/telegram   (Telegram bot)
//   GET  /api/health             →  GET  /health
//   ANY  /api/auth/...           →  ANY  /auth/...             (Google OAuth)
//
// /api/healthz is intentionally NOT proxied — it is handled by the Express
// router below so the deployment health check always succeeds even when
// Jarvis Python is still starting up.
// ─────────────────────────────────────────────────────────────────────────────

app.use("/api/webhooks", (req: Request, res: Response) => {
  // req.url is the path after the mount point, e.g. "/telegram"
  proxyToJarvis(req, res, `/webhooks${req.url}`);
});

app.use("/api/auth", (req: Request, res: Response) => {
  proxyToJarvis(req, res, `/auth${req.url}`);
});

app.get("/api/health", (_req: Request, res: Response) => {
  proxyToJarvis(_req, res, "/health");
});

app.use("/api/me", (req: Request, res: Response) => {
  proxyToJarvis(req, res, `/me${req.url}`);
});

// ── Node.js Express API (body parsers + router) ───────────────────────────────
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

app.use("/api", router);

export default app;
