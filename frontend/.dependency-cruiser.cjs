// Frontend architecture rules (T306). Driven from src/architecture.test.js through the cruise() API.
// Rule names are the stable keys of src/architecture.allowlist.json (`rule|from|to`); do not rename them.
// Paths are relative to frontend/. Test files are not part of the graph: they may reach across layers.
/** @type {import('dependency-cruiser').IConfiguration} */
module.exports = {
  forbidden: [
    {
      name: 'lib-is-pure',
      comment: 'src/lib holds pure helpers: no api, store, composable, component, view, router, vue or pinia.',
      severity: 'error',
      from: { path: '^src/lib/' },
      to: { path: ['^src/(api|stores|composables|components|views|router)/', '(^|/)node_modules/(vue|pinia)/'] },
    },
    {
      name: 'no-upward-layers',
      comment: 'api, stores, composables and lib never import components or views; components never import views.',
      severity: 'error',
      from: { path: '^src/(api|stores|composables|lib|components)/' },
      to: { path: '^src/(components|views)/', pathNot: '^src/$1/' },
    },
    {
      name: 'no-circular',
      comment: 'No import cycles.',
      severity: 'error',
      from: {},
      to: { circular: true },
    },
    {
      name: 'platform-imports-no-module',
      comment: 'The platform (shell) never imports a module; modules contribute through their manifest.',
      severity: 'error',
      from: { path: '^src/platform/' },
      to: { path: '^src/modules/' },
    },
    {
      name: 'modules-only-through-index',
      comment: 'A module imports another module only through its index.js (the manifest), never its internals.',
      severity: 'error',
      from: { path: '^src/modules/([^/]+)/' },
      to: { path: '^src/modules/', pathNot: ['^src/modules/$1/', '^src/modules/[^/]+/index\.js$'] },
    },
  ],
  options: {
    doNotFollow: { path: 'node_modules' },
    exclude: { path: ['\\.test\\.js$', '(^|/)vitest\\.setup\\.js$'] },
    // No tsConfig: the frontend is plain JavaScript and Vue single-file components.
    moduleSystems: ['es6', 'cjs'],
    enhancedResolveOptions: { exportsFields: ['exports'], conditionNames: ['import', 'require', 'node', 'default'] },
  },
}
