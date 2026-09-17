export default function HomePage() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
      <div className="container mx-auto px-4 py-8">
        {/* Header */}
        <header className="mb-8 text-center">
          <h1 className="text-4xl font-bold text-gray-800 mb-2">
            🕵️ OSINT 社交媒体情报采集系统
          </h1>
          <p className="text-lg text-gray-600">
            Open Source Intelligence Gathering Platform
          </p>
        </header>

        {/* Status Banner */}
        <div className="bg-green-100 border-l-4 border-green-500 p-4 mb-8 rounded shadow">
          <div className="flex items-center">
            <span className="text-2xl mr-3">✅</span>
            <div>
              <p className="font-semibold text-green-800">系统状态: 运行中</p>
              <p className="text-sm text-green-700">前端服务已启动 | 版本 v0.1.0 (POC)</p>
            </div>
          </div>
        </div>

        {/* Main Features Grid */}
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
          {/* Feature Card 1 */}
          <div className="bg-white p-6 rounded-lg shadow-md hover:shadow-lg transition-shadow">
            <div className="text-3xl mb-3">📋</div>
            <h3 className="text-xl font-semibold mb-2 text-gray-800">任务管理</h3>
            <p className="text-gray-600 text-sm mb-3">
              创建和管理情报收集任务,支持Telegram、Facebook、Zalo平台
            </p>
            <a href="/tasks" className="text-blue-600 hover:text-blue-800 text-sm font-medium">
              前往任务页面 →
            </a>
          </div>

          {/* Feature Card 2 */}
          <div className="bg-white p-6 rounded-lg shadow-md hover:shadow-lg transition-shadow">
            <div className="text-3xl mb-3">💬</div>
            <h3 className="text-xl font-semibold mb-2 text-gray-800">对话监控</h3>
            <p className="text-gray-600 text-sm mb-3">
              实时查看AI与目标的对话内容,支持人工接管和干预
            </p>
            <a href="/conversations" className="text-blue-600 hover:text-blue-800 text-sm font-medium">
              查看对话 →
            </a>
          </div>

          {/* Feature Card 3 */}
          <div className="bg-white p-6 rounded-lg shadow-md hover:shadow-lg transition-shadow">
            <div className="text-3xl mb-3">🧠</div>
            <h3 className="text-xl font-semibold mb-2 text-gray-800">情报告报</h3>
            <p className="text-gray-600 text-sm mb-3">
              自动提取实体信息,分类标注,可信度评分,去重合并
            </p>
            <a href="/intelligence" className="text-blue-600 hover:text-blue-800 text-sm font-medium">
              查看情报 →
            </a>
          </div>
        </div>

        {/* System Architecture */}
        <div className="bg-white p-6 rounded-lg shadow-md mb-8">
          <h2 className="text-2xl font-bold mb-4 text-gray-800">🏗️ 系统架构</h2>
          <div className="space-y-3 text-sm">
            <div className="flex items-start">
              <span className="text-green-600 mr-2">✓</span>
              <div>
                <strong className="text-gray-700">后端:</strong>
                <span className="text-gray-600 ml-2">FastAPI (Python 3.12+) + Celery + Redis</span>
              </div>
            </div>
            <div className="flex items-start">
              <span className="text-green-600 mr-2">✓</span>
              <div>
                <strong className="text-gray-700">前端:</strong>
                <span className="text-gray-600 ml-2">Next.js 14 + TailwindCSS + WebSocket</span>
              </div>
            </div>
            <div className="flex items-start">
              <span className="text-green-600 mr-2">✓</span>
              <div>
                <strong className="text-gray-700">数据库:</strong>
                <span className="text-gray-600 ml-2">PostgreSQL 16 (结构化) + Redis 7 (缓存/队列)</span>
              </div>
            </div>
            <div className="flex items-start">
              <span className="text-green-600 mr-2">✓</span>
              <div>
                <strong className="text-gray-700">AI引擎:</strong>
                <span className="text-gray-600 ml-2">DeepSeek-V3 LLM (越南语/中文/英文三语支持)</span>
              </div>
            </div>
            <div className="flex items-start">
              <span className="text-green-600 mr-2">✓</span>
              <div>
                <strong className="text-gray-700">平台集成:</strong>
                <span className="text-gray-600 ml-2">Telethon (Telegram) + Playwright (Facebook) + zlapi (Zalo)</span>
              </div>
            </div>
          </div>
        </div>

        {/* Security Features */}
        <div className="bg-white p-6 rounded-lg shadow-md mb-8">
          <h2 className="text-2xl font-bold mb-4 text-gray-800">🔐 安全防护</h2>
          <div className="grid md:grid-cols-2 gap-4">
            <div className="border-l-4 border-blue-500 pl-4">
              <h4 className="font-semibold text-gray-700 mb-1">速率限制</h4>
              <p className="text-sm text-gray-600">每平台独立频率控制,防止触发风控</p>
            </div>
            <div className="border-l-4 border-blue-500 pl-4">
              <h4 className="font-semibold text-gray-700 mb-1">行为模拟</h4>
              <p className="text-sm text-gray-600">打字延迟、阅读延迟、活跃时段模拟真人操作</p>
            </div>
            <div className="border-l-4 border-blue-500 pl-4">
              <h4 className="font-semibold text-gray-700 mb-1">账号健康</h4>
              <p className="text-sm text-gray-600">四级监控(GREEN/YELLOW/RED/BLACK),自动保护</p>
            </div>
            <div className="border-l-4 border-blue-500 pl-4">
              <h4 className="font-semibold text-gray-700 mb-1">内容过滤</h4>
              <p className="text-sm text-gray-600">黑名单关键词拦截,安全护栏机制</p>
            </div>
          </div>
        </div>

        {/* Quick Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          <div className="bg-white p-4 rounded-lg shadow text-center">
            <div className="text-3xl font-bold text-blue-600">3</div>
            <div className="text-sm text-gray-600 mt-1">支持平台</div>
          </div>
          <div className="bg-white p-4 rounded-lg shadow text-center">
            <div className="text-3xl font-bold text-green-600">4</div>
            <div className="text-sm text-gray-600 mt-1">目标类别</div>
          </div>
          <div className="bg-white p-4 rounded-lg shadow text-center">
            <div className="text-3xl font-bold text-purple-600">6</div>
            <div className="text-sm text-gray-600 mt-1">对话状态</div>
          </div>
          <div className="bg-white p-4 rounded-lg shadow text-center">
            <div className="text-3xl font-bold text-orange-600">8+</div>
            <div className="text-sm text-gray-600 mt-1">实体类型</div>
          </div>
        </div>

        {/* Target Categories */}
        <div className="bg-white p-6 rounded-lg shadow-md mb-8">
          <h2 className="text-2xl font-bold mb-4 text-gray-800">🎯 目标分类</h2>
          <div className="grid md:grid-cols-2 gap-4">
            <div className="bg-gray-50 p-4 rounded">
              <h4 className="font-semibold text-gray-700 mb-2">🔍 Private Investigator</h4>
              <p className="text-sm text-gray-600">私人侦探服务,调查监控,跟踪监视</p>
            </div>
            <div className="bg-gray-50 p-4 rounded">
              <h4 className="font-semibold text-gray-700 mb-2">💱 Currency Exchanger</h4>
              <p className="text-sm text-gray-600">换汇服务,转账汇款,外汇交易</p>
            </div>
            <div className="bg-gray-50 p-4 rounded">
              <h4 className="font-semibold text-gray-700 mb-2">💼 Freelancer</h4>
              <p className="text-sm text-gray-600">自由职业者,外包服务,远程工作</p>
            </div>
            <div className="bg-gray-50 p-4 rounded">
              <h4 className="font-semibold text-gray-700 mb-2">📊 Data Seller</h4>
              <p className="text-sm text-gray-600">数据贩卖,客户信息,数据库销售</p>
            </div>
          </div>
        </div>

        {/* Extracted Entities */}
        <div className="bg-white p-6 rounded-lg shadow-md mb-8">
          <h2 className="text-2xl font-bold mb-4 text-gray-800">📦 实体提取能力</h2>
          <div className="flex flex-wrap gap-2">
            <span className="px-3 py-1 bg-blue-100 text-blue-800 rounded-full text-sm">📱 手机号</span>
            <span className="px-3 py-1 bg-green-100 text-green-800 rounded-full text-sm">📧 邮箱</span>
            <span className="px-3 py-1 bg-purple-100 text-purple-800 rounded-full text-sm">💬 Zalo ID</span>
            <span className="px-3 py-1 bg-indigo-100 text-indigo-800 rounded-full text-sm">✈️ Telegram</span>
            <span className="px-3 py-1 bg-pink-100 text-pink-800 rounded-full text-sm">📘 Facebook</span>
            <span className="px-3 py-1 bg-yellow-100 text-yellow-800 rounded-full text-sm">🌐 网站URL</span>
            <span className="px-3 py-1 bg-red-100 text-red-800 rounded-full text-sm">💰 价格信息</span>
            <span className="px-3 py-1 bg-teal-100 text-teal-800 rounded-full text-sm">📍 地址</span>
            <span className="px-3 py-1 bg-orange-100 text-orange-800 rounded-full text-sm">🏦 银行账号</span>
          </div>
        </div>

        {/* Important Notice */}
        <div className="bg-yellow-50 border-l-4 border-yellow-500 p-4 rounded shadow">
          <h3 className="font-semibold text-yellow-800 mb-2">⚠️ 重要声明</h3>
          <p className="text-sm text-yellow-700">
            本系统仅用于<strong>授权的安全研究、渗透测试和教育目的</strong>。使用前必须获得完整的书面授权,遵守当地法律法规(包括越南《网络安全法》),遵循数据最小化原则,保留完整的审计日志。
          </p>
        </div>

        {/* Footer Links */}
        <footer className="mt-8 pt-8 border-t border-gray-200 text-center text-sm text-gray-600">
          <div className="mb-4">
            <a href="http://localhost:8000/docs" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:text-blue-800 mx-2">
              📖 API文档
            </a>
            <span className="text-gray-400">|</span>
            <a href="/tasks" className="text-blue-600 hover:text-blue-800 mx-2">
              📋 任务管理
            </a>
            <span className="text-gray-400">|</span>
            <a href="/conversations" className="text-blue-600 hover:text-blue-800 mx-2">
              💬 对话监控
            </a>
            <span className="text-gray-400">|</span>
            <a href="/intelligence" className="text-blue-600 hover:text-blue-800 mx-2">
              🧠 情报告报
            </a>
          </div>
          <p>版本 v0.1.0 (POC) | 最后更新: 2026-09-14</p>
          <p className="mt-2 text-xs text-gray-500">
            Built with FastAPI + Next.js + DeepSeek AI
          </p>
        </footer>
      </div>
    </div>
  );
}
