import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'OSINT 情报平台',
  description: '社交媒体情报采集系统',
};

const NAV_ITEMS = [
  { href: '/tasks', icon: '📋', label: '任务管理' },
  { href: '/conversations', icon: '💬', label: '对话监控' },
  { href: '/intelligence', icon: '🧠', label: '情报告报' },
  { href: '/accounts', icon: '👤', label: '账号管理' },
  { href: '/groups', icon: '📢', label: '群组管理' },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh">
      <body className="bg-slate-50 text-slate-900 antialiased">
        <div className="flex min-h-screen">
          <nav className="w-60 bg-slate-900 text-white flex flex-col shrink-0">
            <div className="px-5 py-6 border-b border-slate-800">
              <h1 className="text-base font-bold tracking-wide text-white/90">OSINT 情报平台</h1>
              <p className="text-xs text-slate-500 mt-1">Social Intelligence System</p>
            </div>
            <div className="flex-1 px-3 py-4 space-y-1">
              {NAV_ITEMS.map((item) => (
                <a key={item.href} href={item.href}
                  className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-slate-400 hover:text-white hover:bg-slate-800 transition-colors">
                  <span className="text-base opacity-70">{item.icon}</span>
                  {item.label}
                </a>
              ))}
            </div>
            <div className="px-3 pb-4">
              <a href="/live-chat"
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-slate-400 hover:text-white hover:bg-slate-800 transition-colors border-t border-slate-800 pt-3 mt-2">
                <span className="text-base opacity-70">💬</span>
                实时对话演示
              </a>
            </div>
          </nav>
          <main className="flex-1 p-6 overflow-auto">{children}</main>
        </div>
      </body>
    </html>
  );
}
