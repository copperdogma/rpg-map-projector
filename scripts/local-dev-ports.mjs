import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { homedir } from "node:os";

const DEFAULT_ALLOCATION_PATH = "/Users/cam/Documents/Projects/conductor/local-dev-ports.json";

function expandHome(value) {
  if (!value.startsWith("~")) return value;
  if (value === "~") return homedir();
  if (value.startsWith("~/")) return resolve(homedir(), value.slice(2));
  return value;
}

function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}

function writeJsonAtomic(path, value) {
  mkdirSync(dirname(path), { recursive: true });
  const tmpPath = `${path}.${process.pid}.tmp`;
  writeFileSync(tmpPath, `${JSON.stringify(value, null, 2)}\n`);
  renameSync(tmpPath, path);
}

export function findLocalDevAllocationPath() {
  const explicit = process.env.CONDUCTOR_LOCAL_DEV_PORTS_FILE
    || process.env.CONDUCTOR_LOCAL_DEV_PORTS;
  const candidates = explicit ? [explicit] : [DEFAULT_ALLOCATION_PATH];

  for (const candidate of candidates) {
    const resolved = resolve(expandHome(candidate));
    if (existsSync(resolved)) return resolved;
  }

  throw new Error(
    `Missing Conductor local dev port allocation. Set CONDUCTOR_LOCAL_DEV_PORTS_FILE or create ${DEFAULT_ALLOCATION_PATH}.`
  );
}

function rangeSize(range) {
  return range.end - range.start + 1;
}

function maxSlotsFor(project, stride) {
  const ranges = Object.values(project.ranges ?? {});
  if (ranges.length === 0) return 0;
  return Math.min(...ranges.map((range) => Math.floor(rangeSize(range) / stride)));
}

function validateRange(projectKey, serviceName, service, range, port) {
  if (!Number.isInteger(port) || port < range.start || port > range.end) {
    throw new Error(
      `${projectKey}.${serviceName} derived port ${port} is outside ${service.kind} range ${range.start}-${range.end}.`
    );
  }
}

function loadSlotState(path) {
  if (!existsSync(path)) {
    return { version: 1, projects: {} };
  }
  const state = readJson(path);
  if (!state.projects || typeof state.projects !== "object") {
    state.projects = {};
  }
  return state;
}

function assignWorktreeSlot({ allocation, allocationPath, projectKey, project, root }) {
  const stride = allocation.slotStride;
  const maxSlots = maxSlotsFor(project, stride);
  if (maxSlots <= 0) {
    throw new Error(`${projectKey} has no usable worktree slots in ${allocationPath}.`);
  }

  const statePath = resolve(expandHome(allocation.slotStateFile ?? "~/.codex/local-dev-ports.json"));
  const state = loadSlotState(statePath);
  const projectState = state.projects[projectKey] ?? { slots: {} };
  projectState.slots ??= {};

  const existing = projectState.slots[root];
  if (Number.isInteger(existing) && existing >= 0 && existing < maxSlots) {
    state.projects[projectKey] = projectState;
    return { slot: existing, statePath };
  }

  const usedSlots = new Set(
    Object.values(projectState.slots).filter((value) => Number.isInteger(value))
  );
  let slot = null;
  for (let candidate = 0; candidate < maxSlots; candidate += 1) {
    if (!usedSlots.has(candidate)) {
      slot = candidate;
      break;
    }
  }
  if (slot == null) {
    throw new Error(`${projectKey} has no free worktree port slots left in ${statePath}.`);
  }

  projectState.slots[root] = slot;
  state.projects[projectKey] = projectState;
  writeJsonAtomic(statePath, state);
  return { slot, statePath };
}

export function resolveLocalDevPorts(projectKey, rootPath = process.cwd()) {
  const allocationPath = findLocalDevAllocationPath();
  const allocation = readJson(allocationPath);
  const project = allocation.projects?.[projectKey];
  if (!project) {
    throw new Error(`${projectKey} is missing from ${allocationPath}.`);
  }

  const root = resolve(rootPath);
  const primaryRoot = resolve(project.primaryCheckout);
  const isPrimaryCheckout = root === primaryRoot;
  const stride = allocation.slotStride;
  const services = project.services ?? {};
  const ports = {};
  let slot = null;
  let slotStatePath = null;

  if (!Number.isInteger(stride) || stride <= 0) {
    throw new Error(`Invalid slotStride in ${allocationPath}.`);
  }

  if (!isPrimaryCheckout) {
    const assigned = assignWorktreeSlot({ allocation, allocationPath, projectKey, project, root });
    slot = assigned.slot;
    slotStatePath = assigned.statePath;
  }

  for (const [serviceName, service] of Object.entries(services)) {
    if (isPrimaryCheckout) {
      if (Number.isInteger(service.primaryPort)) {
        ports[serviceName] = service.primaryPort;
      }
      continue;
    }

    const range = project.ranges?.[service.kind];
    if (!range) {
      throw new Error(`${projectKey}.${serviceName} references missing ${service.kind} range.`);
    }
    const offset = service.offset ?? 0;
    const port = range.start + slot * stride + offset;
    validateRange(projectKey, serviceName, service, range, port);
    ports[serviceName] = port;
  }

  return {
    allocationPath,
    projectKey,
    projectName: project.name,
    root,
    primaryRoot,
    isPrimaryCheckout,
    slot,
    slotStatePath,
    stride,
    ranges: project.ranges,
    ports
  };
}
