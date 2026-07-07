#!/usr/bin/env node
import { spawnSync } from "node:child_process";

const [, , command, ...args] = process.argv;

function writeJson(payload) {
  process.stdout.write(`${JSON.stringify(payload, null, 2)}\n`);
}

function runNpx(hyperframesArgs) {
  const child = spawnSync("npx", ["--yes", "hyperframes", ...hyperframesArgs], {
    encoding: "utf8",
    maxBuffer: 20 * 1024 * 1024,
  });
  if (child.stdout) process.stdout.write(child.stdout);
  if (child.stderr) process.stderr.write(child.stderr);
  if (child.error) {
    process.stderr.write(`${child.error.message}\n`);
    process.exit(1);
  }
  process.exit(child.status ?? 1);
}

if (!command || command === "help" || command === "--help") {
  process.stdout.write(
    [
      "Usage:",
      "  hyperframes-runner.mjs doctor",
      "  hyperframes-runner.mjs lint <project> --json",
      "  hyperframes-runner.mjs inspect <project> --json --samples 15",
      "  hyperframes-runner.mjs render <project> --quality draft --output <file>",
      "",
    ].join("\n"),
  );
  process.exit(command ? 0 : 2);
}

if (command === "doctor") {
  const npx = spawnSync("npx", ["--version"], { encoding: "utf8" });
  writeJson({
    ok: npx.status === 0,
    node: process.version,
    npx: npx.status === 0,
    npx_version: (npx.stdout || "").trim() || null,
    renderer: "hyperframes",
    adapter: "renderer/hyperframes-runner.mjs",
  });
  process.exit(npx.status === 0 ? 0 : 1);
}

if (command === "lint" || command === "inspect" || command === "render") {
  runNpx([command, ...args]);
}

process.stderr.write(`unsupported renderer command: ${command}\n`);
process.exit(2);
