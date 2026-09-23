import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'OSINT 情报平台',
  description: '社交媒体情报采集系统',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh">
      <body>
        <div className="flex min-h-screen">
          <nav className="w-56 bg-gray-900 text-white p-4 flex flex-col gap-2 shrink-0">
            <h1 className="text-lg font-bold mb-4">🕵️ OSINT 平台</h1>
            <a href="/tasks" className="px-3 py-2 rounded hover:bg-gray-700">📋 任务管理</a>
            <a href="/conversations" className="px-3 py-2 rounded hover:bg-gray-700">💬 对话监控</a>
            <a href="/intelligence" className="px-3 py-2 rounded hover:bg-gray-700">🧠 情报告报</a>
            <a href="/accounts" className="px-3 py-2 rounded hover:bg-gray-700">👤 账号管理</a>
            <a href="/groups" className="px-3 py-2 rounded hover:bg-gray-700">📢 群组管理</a>
            <a href="/live-chat" className="px-3 py-2 rounded hover:bg-gray-700 bg-blue-600">💬 实时对话演示</a>
          </nav>
          <main className="flex-1 p-6">{children}</main>
        </div>
      </body>
    </html>
  );
}
