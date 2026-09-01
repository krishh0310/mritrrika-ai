// Metro, taught about the workspace (Expo's documented monorepo setup).
//
// Without this the app bundles two copies of React and renders nothing: npm
// hoists react-native-web to the workspace root, where the nearest `react` is
// the 19 that apps/web needs, while the app itself resolves the 18 that Expo
// SDK 52 pins in apps/mobile. React refuses to render elements created by a
// different copy of itself -- "A React Element from an older version of React
// was rendered" -- and the screen comes up blank.
//
// `nodeModulesPaths` lists the project's own modules first, and
// `disableHierarchicalLookup` stops Metro walking up the tree behind that
// list, so every module in the graph resolves the same React.
const path = require("node:path");

const { getDefaultConfig } = require("expo/metro-config");

const projectRoot = __dirname;
const workspaceRoot = path.resolve(projectRoot, "../..");

const config = getDefaultConfig(projectRoot);

// Hoisted dependencies live at the workspace root, so Metro has to watch it.
config.watchFolders = [workspaceRoot];

config.resolver.nodeModulesPaths = [
  path.resolve(projectRoot, "node_modules"),
  path.resolve(workspaceRoot, "node_modules"),
];
config.resolver.disableHierarchicalLookup = true;

module.exports = config;
