#!/usr/bin/env node

import { execFileSync, spawn } from "node:child_process";
import http from "node:http";
import { dirname, join, resolve } from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import { resolveLocalDevPorts } from "./local-dev-ports.mjs";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const DEFAULT_HOST = "127.0.0.1";
const runtime = resolveLocalDevPorts("rpg-map-projector", ROOT);
const UI_PORT = Number.parseInt(
  process.env.RPG_MAP_PROJECTOR_UI_PORT || process.env.FRONTEND_PORT || String(runtime.ports.ui),
  10
);

function localBin(name) {
  const suffix = process.platform === "win32" ? ".cmd" : "";
  return join(ROOT, "node_modules", ".bin", `${name}${suffix}`);
}

const SERVICES = {
  ui: {
    aliases: ["app", "vite"],
    label: "RPG Map Projector UI",
    port: UI_PORT,
    host: process.env.RPG_MAP_PROJECTOR_UI_HOST || DEFAULT_HOST,
    healthPath: "/",
    openPath: "/",
    projectorPath: "/projector.html",
    command: (service) => [localBin("vite"), ["--host", service.host, "--port", String(service.port), "--strictPort"]],
    env: (service) => ({
      RPG_MAP_PROJECTOR_UI_PORT: String(service.port),
      FRONTEND_PORT: String(service.port)
    }),
    isExpectedHealth: (response) => response.status === 200 && response.text.includes("RPG Map Projector")
  }
};

const TARGETS = {
  app: ["ui"],
  ui: ["ui"],
  all: ["ui"]
};

function usage() {
  console.log(`Usage:
  node scripts/local-service.mjs status [app|ui|all]
  node scripts/local-service.mjs start [app|ui] [--restart|--takeover]
  node scripts/local-service.mjs stop [app|ui|all] [--force]

Recommended commands:
  npm run local:app
  npm run local:status
  npm run local:stop`);
}

function resolveTarget(target = "app") {
  return TARGETS[target] ?? null;
}

function serviceUrl(service, route = "") {
  return `http://${service.host}:${service.port}${route}`;
}

function listenerPids(port) {
  try {
    return execFileSync("lsof", [`-tiTCP:${port}`, "-sTCP:LISTEN"], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"]
    }).split("\n").map((line) => line.trim()).filter(Boolean);
  } catch {
    return [];
  }
}

function processCommand(pid) {
  try {
    return execFileSync("ps", ["-p", String(pid), "-o", "command="], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"]
    }).trim();
  } catch {
    return "";
  }
}

function processCwd(pid) {
  try {
    const output = execFileSync("lsof", ["-a", "-p", String(pid), "-d", "cwd", "-Fn"], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"]
    });
    const line = output.split("\n").find((entry) => entry.startsWith("n"));
    return line ? resolve(line.slice(1)) : "";
  } catch {
    return "";
  }
}

function sameCheckoutProcess(pid) {
  const cwd = processCwd(pid);
  return cwd === ROOT || cwd.startsWith(`${ROOT}/`);
}

function describePids(pids) {
  return pids.map((pid) => {
    const command = processCommand(pid) || "(command unavailable)";
    const cwd = processCwd(pid);
    return `  pid ${pid}: ${command}${cwd ? ` cwd=${cwd}` : ""}`;
  }).join("\n");
}

function sleep(ms) {
  return new Promise((resolveSleep) => {
    setTimeout(resolveSleep, ms);
  });
}

async function probeService(service) {
  return new Promise((resolveProbe) => {
    const req = http.get(serviceUrl(service, service.healthPath), { timeout: 800 }, (res) => {
      let text = "";
      res.setEncoding("utf8");
      res.on("data", (chunk) => {
        text += chunk;
      });
      res.on("end", () => {
        resolveProbe({
          reachable: true,
          expected: service.isExpectedHealth({ status: res.statusCode ?? 0, text }),
          status: res.statusCode ?? 0
        });
      });
    });
    req.on("timeout", () => {
      req.destroy();
      resolveProbe({ reachable: false, expected: false, status: 0 });
    });
    req.on("error", () => {
      resolveProbe({ reachable: false, expected: false, status: 0 });
    });
  });
}

async function stopPids(pids, { force = false } = {}) {
  for (const pid of pids) {
    try {
      process.kill(Number(pid), "SIGTERM");
    } catch {
      // Process may already be gone.
    }
  }
  await sleep(350);
  if (!force) return;
  for (const pid of pids) {
    try {
      process.kill(Number(pid), 0);
      process.kill(Number(pid), "SIGKILL");
    } catch {
      // Process may already be gone.
    }
  }
}

async function status(target = "app") {
  const serviceNames = resolveTarget(target);
  if (!serviceNames) {
    usage();
    process.exit(2);
  }

  console.log("RPG Map Projector local runtime");
  console.log(`  root: ${ROOT}`);
  console.log(`  allocation: ${runtime.allocationPath}`);
  console.log(`  slot: ${runtime.isPrimaryCheckout ? "primary" : runtime.slot}`);
  if (runtime.slotStatePath) console.log(`  slot state: ${runtime.slotStatePath}`);

  for (const serviceName of serviceNames) {
    const service = SERVICES[serviceName];
    const probe = await probeService(service);
    const pids = listenerPids(service.port);
    const sameCheckout = pids.length === 0 || pids.every(sameCheckoutProcess);
    const state = probe.expected
      ? sameCheckout ? "ready" : "ready in another checkout"
      : pids.length > 0 ? "occupied" : "stopped";
    console.log(`  ${serviceName}: ${state} ${serviceUrl(service, service.openPath)}`);
    if (service.projectorPath) {
      console.log(`    projector: ${serviceUrl(service, service.projectorPath)}`);
    }
    if (pids.length > 0) console.log(describePids(pids));
  }
}

async function start(target = "app", options = {}) {
  const serviceNames = resolveTarget(target);
  if (!serviceNames) {
    usage();
    process.exit(2);
  }

  for (const serviceName of serviceNames) {
    const service = SERVICES[serviceName];
    const pids = listenerPids(service.port);
    const sameCheckout = pids.length === 0 || pids.every(sameCheckoutProcess);
    const probe = await probeService(service);

    if (probe.expected && sameCheckout && !options.restart) {
      console.log(`${service.label} already ready: ${serviceUrl(service, service.openPath)}`);
      continue;
    }

    if (pids.length > 0 && !sameCheckout && !options.takeover) {
      throw new Error(
        `${service.label} port ${service.port} is owned by another checkout/process. Use --takeover only if intentional.\n${describePids(pids)}`
      );
    }

    if (pids.length > 0 && (options.restart || options.takeover || sameCheckout)) {
      await stopPids(pids, { force: options.takeover });
    }

    const [cmd, args] = service.command(service);
    const child = spawn(cmd, args, {
      cwd: ROOT,
      detached: true,
      stdio: "ignore",
      env: { ...process.env, ...service.env(service) }
    });
    child.unref();

    let ready = false;
    for (let attempt = 0; attempt < 40; attempt += 1) {
      await sleep(250);
      const nextProbe = await probeService(service);
      if (nextProbe.expected) {
        ready = true;
        break;
      }
    }
    if (!ready) {
      throw new Error(`${service.label} did not become ready on ${serviceUrl(service, service.healthPath)}.`);
    }
    console.log(`${service.label} ready: ${serviceUrl(service, service.openPath)}`);
    if (service.projectorPath) {
      console.log(`Projector view: ${serviceUrl(service, service.projectorPath)}`);
    }
  }
}

async function stop(target = "app", options = {}) {
  const serviceNames = resolveTarget(target);
  if (!serviceNames) {
    usage();
    process.exit(2);
  }

  for (const serviceName of serviceNames) {
    const service = SERVICES[serviceName];
    const pids = listenerPids(service.port);
    if (pids.length === 0) {
      console.log(`${service.label} already stopped.`);
      continue;
    }
    const sameCheckout = pids.every(sameCheckoutProcess);
    if (!sameCheckout && !options.force) {
      throw new Error(
        `${service.label} port ${service.port} is owned by another checkout/process. Use --force only if intentional.\n${describePids(pids)}`
      );
    }
    await stopPids(pids, { force: options.force });
    console.log(`${service.label} stopped.`);
  }
}

async function main() {
  const [command = "status", target = "app", ...flags] = process.argv.slice(2);
  const options = {
    restart: flags.includes("--restart"),
    takeover: flags.includes("--takeover"),
    force: flags.includes("--force")
  };

  if (command === "status") return status(target);
  if (command === "start") return start(target, options);
  if (command === "stop") return stop(target, options);

  usage();
  process.exit(2);
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
