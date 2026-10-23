import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 构建产物直接放进 Python 包，replay studio 从那里提供；文件名不带哈希，免得每次构建都在仓库里留一堆改名。
// 开发时 npm run dev，接口转给 replay studio --no-browser 开着的服务。
const backend = 'http://127.0.0.1:8766'

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../src/rlyeh/studio/static',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        entryFileNames: 'assets/studio.js',
        chunkFileNames: 'assets/[name].js',
        assetFileNames: 'assets/[name][extname]',
      },
    },
  },
  server: {
    proxy: Object.fromEntries(['/api', '/files', '/voices', '/review', '/player'].map((p) => [p, backend])),
  },
})
