import { spawn } from "child_process";
import app from "./app";

const rawPort = process.env["PORT"];

if (!rawPort) {
  throw new Error(
    "PORT environment variable is required but was not provided.",
  );
}

const port = Number(rawPort);

if (Number.isNaN(port) || port <= 0) {
  throw new Error(`Invalid PORT value: "${rawPort}"`);
}

if (process.env.NODE_ENV === "production") {
  const workspaceRoot = process.cwd();
  const jarvisPort = 8000;

  console.log(
    `Starting Jarvis Pessoal from ${workspaceRoot} on port ${jarvisPort}...`,
  );

  const jarvisEnv = { ...process.env };
  delete jarvisEnv["PORT"];

  const jarvis = spawn(
    "uvicorn",
    [
      "app.main:app",
      "--host",
      "0.0.0.0",
      "--port",
      String(jarvisPort),
      "--workers",
      "1",
    ],
    {
      cwd: workspaceRoot,
      stdio: "inherit",
      env: jarvisEnv,
    },
  );

  jarvis.on("error", (err) => {
    console.error("Failed to start Jarvis:", err.message);
  });

  jarvis.on("exit", (code, signal) => {
    if (code !== 0) {
      console.error(`Jarvis exited with code ${code}, signal ${signal}`);
    }
  });
}

app.listen(port, () => {
  console.log(`Server listening on port ${port}`);
});
