#!/bin/bash
# 聊天服务管理脚本

cd "$(dirname "$0")"
source venv/bin/activate

case "$1" in
    start)
        echo "=========================================="
        echo "🚀 启动持久化聊天机器人"
        echo "=========================================="

        # 检查session是否存在
        if [ ! -f "sessions/printer.session" ]; then
            echo "❌ Session文件不存在"
            echo ""
            echo "请先登录:"
            echo "  python quick_login.py"
            echo ""
            exit 1
        fi

        # 检查是否已在运行
        if [ -f "chat_demo.pid" ]; then
            PID=$(cat chat_demo.pid)
            if ps -p $PID > /dev/null 2>&1; then
                echo "⚠️  服务已在运行 (PID: $PID)"
                echo ""
                echo "停止旧服务: ./start_chat_service.sh stop"
                echo ""
                exit 1
            else
                echo "清理过期PID文件"
                rm -f chat_demo.pid
            fi
        fi

        # 启动服务
        echo "启动中..."
        nohup python persistent_chat_demo.py start > logs/chat_demo.out 2>&1 &
        NEW_PID=$!
        echo $NEW_PID > chat_demo.pid

        sleep 3

        # 检查启动状态
        if ps -p $NEW_PID > /dev/null 2>&1; then
            echo "✅ 服务已启动 (PID: $NEW_PID)"
            echo ""
            echo "查看日志: tail -f logs/chat_demo.log"
            echo "停止服务: ./start_chat_service.sh stop"
            echo ""
        else
            echo "❌ 启动失败,查看日志:"
            cat logs/chat_demo.out
            echo ""
            exit 1
        fi
        ;;

    stop)
        echo "⏹️  停止聊天机器人..."

        if [ -f "chat_demo.pid" ]; then
            PID=$(cat chat_demo.pid)
            kill $PID 2>/dev/null
            rm -f chat_demo.pid
            echo "✅ 已停止进程 $PID"
        else
            echo "⚠️  未找到PID文件"
            pkill -f persistent_chat_demo.py
            echo "✅ 已尝试停止所有相关进程"
        fi
        ;;

    status)
        if [ -f "chat_demo.pid" ]; then
            PID=$(cat chat_demo.pid)
            if ps -p $PID > /dev/null 2>&1; then
                echo "✅ 服务运行中 (PID: $PID)"
                echo ""
                echo "最近日志:"
                tail -5 logs/chat_demo.log 2>/dev/null || echo "无日志"
            else
                echo "❌ PID文件存在但进程不存在"
                rm -f chat_demo.pid
            fi
        else
            echo "❌ 服务未运行"
        fi
        ;;

    logs)
        if [ -f "logs/chat_demo.log" ]; then
            tail -f logs/chat_demo.log
        else
            echo "❌ 日志文件不存在"
        fi
        ;;

    login)
        shift
        python quick_login.py "$@"
        ;;

    *)
        echo "用法: $0 {start|stop|status|logs|login [会话名 ...]}"
        echo ""
        echo "命令说明:"
        echo "  start   - 启动聊天机器人"
        echo "  stop    - 停止聊天机器人"
        echo "  status  - 查看运行状态"
        echo "  logs    - 查看实时日志"
        echo "  login   - 依次登录，如: $0 login test1 test2 test3"
        echo ""
        exit 1
        ;;
esac
