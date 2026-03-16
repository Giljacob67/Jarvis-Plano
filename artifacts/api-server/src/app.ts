import * as http from "http";
import express, { type Express, type NextFunction, type Request, type Response } from "express";
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

// All /api/* requests except /api/healthz are forwarded to Jarvis Python (port 8000).
// The /api prefix is stripped before forwarding:
//   /api/webhooks/telegram  →  /webhooks/telegram
//   /api/health             →  /health
//   /api/auth/google/start  →  /auth/google/start
// Must come BEFORE body parsers so raw body is available for piping.
app.use("/api", (req: Request, res: Response, next: NextFunction) => {
  if (req.path === "/healthz") {
    return next();
  }
  proxyToJarvis(req, res, req.url);
});

app.use(express.json());
app.use(express.urlencoded({ extended: true }));

app.use("/api", router);

export default app;
