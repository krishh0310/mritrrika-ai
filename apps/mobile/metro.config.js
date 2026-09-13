// Metro, taught about the monorepo.
//
// The default config watches only apps/mobile, so an import reaching into
// packages/ resolves under tsc and then fails at bundle time -- a break that
// only shows up in `expo export`, never in a typecheck. The UI message
// catalogues are shared with the web app deliberately: two copies of the same
// translations drift, and the drift is invisible until a user reads it.
//
// Only the catalogue files are imported, never packages/ui's barrel, which
// pulls in DOM components React Native cannot render.

const path = require("path");
const { getDefaultConfig } = require("expo/metro-config");

const projectRoot = __dirname;
const workspaceRoot = path.resolve(projectRoot, "../..");

const config = getDefaultConfig(projectRoot);

config.watchFolders = [workspaceRoot];
config.resolver.nodeModulesPaths = [
  path.resolve(projectRoot, "node_modules"),
  path.resolve(workspaceRoot, "node_modules"),
];
// Hoisted dependencies must not be resolved twice; two copies of React is the
// classic symptom (hooks throwing "invalid hook call" at runtime only).
config.resolver.disableHierarchicalLookup = true;

module.exports = config;
