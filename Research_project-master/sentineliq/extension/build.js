import { build } from 'esbuild'

build({
  entryPoints: ['extension/firebase-auth-init.js'],
  bundle: true,
  outfile: 'extension/vendor/firebase-bundle.js',
  format: 'iife',
  globalName: 'FirebaseAuthBundle',
  define: { 'process.env.NODE_ENV': '"production"' },
  minify: true,
  target: ['chrome100'],
}).catch(() => process.exit(1))
