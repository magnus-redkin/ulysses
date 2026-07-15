import tailwindcss from '@tailwindcss/vite';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';
import dotenv from 'dotenv';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Загружаем .env из папки на уровень выше (../)
dotenv.config({ path: path.resolve(__dirname, '../.env') });

// console.log('📁 Загружаем .env из:', path.resolve(__dirname, '../.env'));
// console.log('📋 BOT_TOKEN:', process.env.BOT_TOKEN ? '✅ Найден' : '❌ Не найден');

export default defineConfig({
    plugins: [tailwindcss(), sveltekit()],
    server: {
        port: 5173,
	strictPort: true,
        allowedHosts: ['ulysses.best', 'www.ulysses.best'],
    }
});
