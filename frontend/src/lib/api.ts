/**
 * 前端 API 客户端 / WebSocket 客户端 / 共享类型与演示数据。
 *
 * ⚠️ 背景说明：本文件长期缺失。原因是仓库根 .gitignore 里有一条 Python 产物规则
 * `lib/`，它把 frontend/src/lib/ 整个目录一起忽略了，于是本文件从未被提交，
 * 6 个页面全部 import 失败、前端根本编译不过。现已把规则改为锚定根目录的 `/lib/`，
 * 并按各页面的实际用法重建本文件。
 *
 * 约定：
 * - REST 基地址：NEXT_PUBLIC_API_URL，默认 http://localhost:8000/api/v1
 * - WebSocket：NEXT_PUBLIC_WS_URL，默认 ws://localhost:8000/ws
 */

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

export const WS_URL =
  process.env.NEXT_PUBLIC_WS_URL ||
  `${API_BASE.replace(/^http/, 'ws').replace(/\/api\/v1\/?$/, '')}/ws`;

// ─────────────────────────────────────────────────────
// 类型定义（与 backend/app/schemas/schemas.py 对齐）
// ─────────────────────────────────────────────────────

export type Platform = 'telegram' | 'facebook' | 'zalo';
export type AccountHealth = 'green' | 'yellow' | 'red' | 'black';

export interface ReplyPolicy {
  private: boolean;
  groups: boolean;
  channels: boolean;
  bots: boolean;
}

export interface Account {
  /** 账号标识：即 sessions/ 目录下的会话名，如 printer */
  id: string;
  platform: Platform;
  username: string;
  display_name?: string;
  health: AccountHealth;
  reply_policy?: ReplyPolicy;
  paused?: boolean;
  persona?: string;
  proxy_url?: string;
  is_active?: boolean;
  /** 后端返回的是文件时间戳（秒），也可能是 ISO 字符串 */
  last_action_at?: string | number;
  created_at?: string | number;
  session_file?: string;
}

export interface PersonaPreset {
  key: string;
  name: string;
  desc: string;
  tone?: string;
}

export interface ServiceStatus {
  platform: string;
  /** 服务的中文名，例如「Telegram 常驻在线服务」 */
  label?: string;
  running: boolean;
  pid?: number | null;
  script?: string;
  /** 仅常驻在线服务：它当前挂载的账号（sessions/ 下的会话名） */
  session?: string | null;
}

export interface Task {
  id: string;
  name: string;
  platform: Platform;
  category: string;
  keywords: string[];
  target_region?: string | null;
  status: 'pending' | 'running' | 'paused' | 'completed' | 'failed' | string;
  /** 含 last_run 摘要：searched_keywords / found_groups / joined_groups / conversations */
  config?: {
    schedule?: {
      enabled?: boolean;
      mode?: 'daily' | 'interval' | string;
      at?: string;
      every_minutes?: number;
      next_run_at?: string;
      last_run_at?: string;
      last_skipped_reason?: string | null;
    } | null;
    progress?: {
      stage?: string;
      keyword?: string;
      group?: string;
      target?: string;
      members?: number;
      account?: string;
    } | null;
    last_run?: {
      account?: string | null;
      searched_keywords?: number;
      found_groups?: number;
      joined_groups?: number;
      members_found?: number;
      conversations?: number;
      finished_at?: string;
      error?: string | null;
      warning?: string | null;
    };
    [key: string]: unknown;
  };
  /** 后端 TaskResponse 必返，页面会直接 new Date() 用它 */
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  conversation_id?: string;
  direction: 'inbound' | 'outbound';
  content: string;
  language?: string | null;
  created_at: string;
}

export interface Conversation {
  id: string;
  account_id: string;
  account_name?: string | null;
  task_id?: string;
  target_user_id: string;
  target_display_name?: string | null;
  state: string;
  turn_count: number;
  context_summary?: string | null;
  started_at: string;
  ended_at?: string | null;
  messages: Message[];
}

export interface IntelligenceRecord {
  id: string;
  task_id?: string;
  platform: Platform;
  target_user_id: string;
  display_name?: string | null;
  profile_url?: string | null;
  category: string;
  confidence: number;
  signals?: string[];
  extracted_contacts?: Record<string, unknown>;
  business_info?: Record<string, unknown>;
  activity_status: string;
  review_status: string;
  platforms?: string[] | null;
  operator_notes?: string | null;
  last_seen?: string | null;
  collected_at: string;
}

export interface SessionCheckResult {
  valid: boolean;
  message: string;
  platform?: string;
  details?: Record<string, unknown>;
}

export interface TelegramVerifyResult {
  status: 'success' | 'need_password' | 'failed' | string;
  username?: string;
  user_id?: number;
  message?: string;
}

export interface GroupSearchResult {
  results: Array<{
    group_id: string;
    name: string;
    member_count: number;
    description: string;
  }>;
  keywords_used: string[];
}

/** WebSocket 推送的消息体（守护进程 → FastAPI → 前端） */
export interface WSMessage {
  type: string;
  direction: 'inbound' | 'outbound';
  content: string;
  sender_id?: string;
  sender_name: string;
  account: string;
  platform: string;
  timestamp: string;
  [key: string]: unknown;
}

export type WSHandler = (message: WSMessage) => void;

// ─────────────────────────────────────────────────────
// REST 客户端
// ─────────────────────────────────────────────────────

export interface FetchOptions extends RequestInit {
  /** 超时毫秒数，默认 15s；群组搜索这类慢接口页面会显式传 60s */
  timeout?: number;
}

/**
 * 统一的 fetch 封装：拼 API_BASE、带 JSON 头、带超时、失败时抛出可读错误。
 * 后端抛 HTTPException 时把 detail 提出来当作 Error.message，
 * 页面正是靠 message 里的文字做提示的。
 */
export async function fetchAPI<T = any>(
  path: string,
  options: FetchOptions = {},
): Promise<T> {
  const { timeout = 15000, headers, ...rest } = options;
  const url = path.startsWith('http')
    ? path
    : `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(url, {
      cache: 'no-store',
      ...rest,
      headers: {
        'Content-Type': 'application/json',
        ...(headers || {}),
      },
      signal: controller.signal,
    });

    if (!response.ok) {
      let detail = `${response.status} ${response.statusText}`;
      try {
        const body = await response.json();
        if (body?.detail) {
          detail =
            typeof body.detail === 'string'
              ? body.detail
              : JSON.stringify(body.detail);
        }
      } catch {
        /* 响应体不是 JSON，保留状态码信息 */
      }
      throw new Error(detail);
    }

    if (response.status === 204) return undefined as T;
    const text = await response.text();
    return (text ? JSON.parse(text) : undefined) as T;
  } catch (error: any) {
    if (error?.name === 'AbortError') {
      throw new Error(`请求超时（${timeout}ms）：${url}`);
    }
    if (error instanceof TypeError) {
      // 浏览器的 fetch 在"连不上"和"响应被拦截（如缺少跨域头）"两种情况下
      // 都会抛 TypeError，这里把可能性都提示出来，避免误导成单一原因
      throw new Error(
        '无法读取后端响应：可能是 API 未启动，也可能是响应被浏览器拦截（跨域）。请查看后端日志 api.err',
      );
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * 下载导出文件：fetch → blob → 触发浏览器保存。
 * 后端返回错误 JSON 时抛可读错误，避免浏览器跳到错误页。
 */
export async function downloadExport(path: string): Promise<void> {
  const url = `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`;
  const response = await fetch(url, { headers: { 'Content-Type': 'application/json' } });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body?.detail) {
        detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      /* 响应体不是 JSON */
    }
    throw new Error(detail);
  }

  const blob = await response.blob();
  const disposition = response.headers.get('Content-Disposition') || '';
  const match = disposition.match(/filename="?([^";]+)"?/);
  const filename = match?.[1] || 'export.csv';

  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = objectUrl;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(objectUrl);
}

// ─────────────────────────────────────────────────────
// WebSocket 客户端
// ─────────────────────────────────────────────────────

/**
 * 频道模型与后端 main.py 一致：global / task:<id> / conv:<id>。
 * 断线后会按 2s→30s 指数退避重连；首个连接失败时 promise 会 reject，
 * 页面据此提示"后端不可达"，重连仍会继续，后端起来后自动恢复实时数据。
 */
export class WSClient {
  private ws: WebSocket | null = null;
  private handlers = new Map<string, Set<WSHandler>>();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private attempts = 0;
  private shouldReconnect = false;
  private channel = 'global';

  get connected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  connect(channel: string = 'global'): Promise<void> {
    this.channel = channel;
    this.shouldReconnect = true;

    if (
      this.ws &&
      (this.ws.readyState === WebSocket.OPEN ||
        this.ws.readyState === WebSocket.CONNECTING)
    ) {
      return Promise.resolve();
    }

    return new Promise<void>((resolve, reject) => {
      let socket: WebSocket;
      try {
        socket = new WebSocket(WS_URL);
      } catch (error) {
        reject(error);
        return;
      }
      this.ws = socket;

      socket.onopen = () => {
        this.attempts = 0;
        if (this.channel !== 'global') {
          socket.send(JSON.stringify({ type: 'subscribe', channel: this.channel }));
        }
        resolve();
      };

      socket.onmessage = (event: MessageEvent) => {
        let payload: any;
        try {
          payload = JSON.parse(event.data as string);
        } catch {
          return;
        }
        const type = payload?.type as string | undefined;
        if (type) this.dispatch(type, payload);
        this.dispatch('*', payload);
      };

      socket.onerror = () => {
        reject(new Error('WebSocket 连接失败，请确认后端服务已启动'));
      };

      socket.onclose = () => {
        this.ws = null;
        if (this.shouldReconnect) this.scheduleReconnect();
      };
    });
  }

  disconnect(): void {
    this.shouldReconnect = false;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.attempts = 0;
    const socket = this.ws;
    this.ws = null;
    if (socket) {
      socket.onclose = null;
      socket.onerror = null;
      socket.onmessage = null;
      socket.close();
    }
    this.handlers.clear();
  }

  on(event: string, handler: WSHandler): void {
    if (!this.handlers.has(event)) this.handlers.set(event, new Set());
    this.handlers.get(event)!.add(handler);
  }

  off(event: string, handler: WSHandler): void {
    this.handlers.get(event)?.delete(handler);
  }

  /** 切换订阅频道（后端支持 global / task:<id> / conv:<id>） */
  subscribe(channel: string): void {
    this.channel = channel;
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: 'subscribe', channel }));
    }
  }

  private dispatch(type: string, payload: any): void {
    this.handlers.get(type)?.forEach((handler) => {
      try {
        handler(payload as WSMessage);
      } catch (error) {
        console.error(`WebSocket 处理器异常 (${type}):`, error);
      }
    });
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) return;
    const delay = Math.min(2000 * 2 ** this.attempts, 30000);
    this.attempts += 1;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect(this.channel).catch(() => {
        /* 失败会再次走 onclose → scheduleReconnect */
      });
    }, delay);
  }
}

/** 全局单例：多个页面复用同一条连接 */
export const wsClient = new WSClient();

// ─────────────────────────────────────────────────────
// 账号相关接口
// ─────────────────────────────────────────────────────

export const accountAPI = {
  list: () => fetchAPI<Account[]>('/accounts'),

  delete: (accountId: string) =>
    fetchAPI<{ status: string }>(`/accounts/${accountId}`, { method: 'DELETE' }),

  updateDisplayName: (accountId: string, displayName: string) =>
    fetchAPI(`/accounts/${accountId}`, {
      method: 'PATCH',
      body: JSON.stringify({ display_name: displayName }),
    }),

  updateReplyPolicy: (accountId: string, policy: ReplyPolicy) =>
    fetchAPI(`/accounts/${accountId}`, {
      method: 'PATCH',
      body: JSON.stringify({ reply_policy: policy }),
    }),

  setPaused: (accountId: string, paused: boolean) =>
    fetchAPI(`/accounts/${accountId}`, {
      method: 'PATCH',
      body: JSON.stringify({ paused }),
    }),

  setPersona: (accountId: string, persona: string) =>
    fetchAPI(`/accounts/${accountId}`, {
      method: 'PATCH',
      body: JSON.stringify({ persona }),
    }),

  listPersonas: () =>
    fetchAPI<{ personas: PersonaPreset[] }>('/accounts/personas'),

  checkSession: (accountId: string) =>
    fetchAPI<SessionCheckResult>(`/accounts/${accountId}/check-session`, {
      method: 'POST',
      timeout: 30000,
    }),

  telegramTestConnection: (sessionName?: string) =>
    fetchAPI<{ connected: boolean; message: string }>(
      '/accounts/telegram/test-connection',
      {
        method: 'POST',
        body: JSON.stringify({ session_name: sessionName || '' }),
        timeout: 30000,
      },
    ),

  telegramSendCode: (phone: string, sessionName: string) =>
    fetchAPI('/accounts/telegram/send-code', {
      method: 'POST',
      body: JSON.stringify({ phone, session_name: sessionName }),
      timeout: 60000,
    }),

  telegramVerifyCode: (
    sessionName: string,
    code: string,
    password?: string,
  ) =>
    fetchAPI<TelegramVerifyResult>('/accounts/telegram/verify-code', {
      method: 'POST',
      body: JSON.stringify({ session_name: sessionName, code, password }),
      timeout: 60000,
    }),

  facebookLoginStart: (sessionName: string) =>
    fetchAPI('/accounts/facebook/login', {
      method: 'POST',
      body: JSON.stringify({ session_name: sessionName }),
      timeout: 30000,
    }),

  facebookLoginComplete: (sessionName: string) =>
    fetchAPI<{ status: string; message: string }>(
      '/accounts/facebook/login-complete',
      {
        method: 'POST',
        body: JSON.stringify({ session_name: sessionName }),
        timeout: 30000,
      },
    ),

  zaloLogin: (phone: string, password: string, sessionName: string) =>
    fetchAPI('/accounts/zalo/login', {
      method: 'POST',
      body: JSON.stringify({ phone, password, session_name: sessionName }),
      timeout: 60000,
    }),
};

// ─────────────────────────────────────────────────────
// 平台服务（常驻聊天进程）接口
// ─────────────────────────────────────────────────────

export const serviceAPI = {
  status: () => fetchAPI<ServiceStatus[]>('/services/status'),

  start: (platform: string, session?: string) =>
    fetchAPI<{ status: string; pid?: number; platform: string }>(
      `/services/${platform}/start${session ? `?session=${encodeURIComponent(session)}` : ''}`,
      { method: 'POST', timeout: 30000 },
    ),

  stop: (platform: string) =>
    fetchAPI<{ status: string; pid?: number; platform: string }>(
      `/services/${platform}/stop`,
      { method: 'POST', timeout: 30000 },
    ),

  logs: (platform: string, lines: number = 50) =>
    fetchAPI<{ platform: string; logs: string[]; message?: string }>(
      `/services/${platform}/logs?lines=${lines}`,
    ),
};
