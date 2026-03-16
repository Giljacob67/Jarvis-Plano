import * as http from "http";
import express, { type Express, type NextFunction, type Request, type Response } from "express";
import cors from "cors";
import router from "./routes";

const JARVIS_HOST = "127.0.0.1";
const JARVIS_PORT = 8000;

function proxyToJarvis(req: Request, res: Response): void {
  const options: http.RequestOptions = {
    hostname: JARVIS_HOST,
    port: JARVIS_PORT,
    path: req.url,
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

if (process.env.NODE_ENV === "production") {
  app.use((req: Request, res: Response, next: NextFunction) => {
    if (!req.path.startsWith("/api")) {
      proxyToJarvis(req, res);
    } else {
      next();
    }
  });
}

app.use(express.json());
app.use(express.urlencoded({ extended: true }));

app.use("/api", router);

export default app;
