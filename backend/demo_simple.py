"""
简化演示脚本 - 验证核心功能(无需Telegram连接)

演示内容:
1. 算术题验证机制
2. 养号策略限制检查
3. 完整工作流程说明
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.conversation.verification import verification_manager
from app.services.security.account_warming import warming_manager


def demo_verification():
    """演示: 算术题验证机制"""
    print("=" * 70)
    print(" 演示1: 算术题验证机制")
    print("=" * 70)
    
    test_user_id = "test_user_12345"
    
    print(f"\n👤 模拟新用户: {test_user_id}")
    
    # 第一步: 发送验证问题
    challenge_msg = verification_manager.get_challenge_message(test_user_id)
    if challenge_msg:
        print(f"\n📩 系统发送验证消息:")
        for line in challenge_msg.split('\n'):
            print(f"   {line}")
    
    # 第二步: 用户回答错误
    print(f"\n❌ 用户尝试回答: '999' (错误答案)")
    is_correct = verification_manager.check_answer(test_user_id, "999")
    print(f"   验证结果: {'✅ 通过' if is_correct else '❌ 失败'}")
    
    # 第三步: 获取正确答案并回答
    challenge = verification_manager._challenges.get(test_user_id)
    if challenge:
        correct_answer = str(challenge.answer)
        print(f"\n✅ 用户回答: '{correct_answer}' (正确答案: {challenge.question})")
        is_correct = verification_manager.check_answer(test_user_id, correct_answer)
        print(f"   验证结果: {'✅ 通过' if is_correct else '❌ 失败'}")
        
        if is_correct:
            print(f"   🎉 验证成功!用户可以开始对话")
    
    # 第四步: 再次验证(应该直接通过)
    print(f"\n🔄 同一用户再次发起对话...")
    is_verified = verification_manager.is_verified(test_user_id)
    print(f"   验证状态: {'✅ 已验证,跳过验证步骤' if is_verified else '⚠️ 需要重新验证'}")
    
    print("\n✅ 验证机制演示完成\n")


def demo_warming_strategy():
    """演示: 养号策略限制检查"""
    print("=" * 70)
    print("️ 演示2: 养号策略限制检查")
    print("=" * 70)
    
    # 创建不同阶段的测试账号
    test_accounts = [
        ("new_account", 3),      # 新号期
        ("warming_account", 15), # 温号期
        ("stable_account", 60),  # 稳定期
        ("mature_account", 120), # 成熟期
    ]
    
    for account_id, age_days in test_accounts:
        created_at = datetime.now() - timedelta(days=age_days)
        profile = warming_manager.create_profile(
            account_id=account_id,
            created_at=created_at,
            ip_region="Vietnam-HCM",
        )
        
        # 设置必要配置(仅新号需要)
        if age_days < 7:
            warming_manager.update_settings(
                account_id,
                interface_localized=True,
                contacts_sync_disabled=True,
                two_factor_enabled=True,
                auto_delete_enabled=True,
                privacy_settings_complete=True,
            )
        
        print(f"\n📱 账号: {account_id} (账号年龄: {age_days}天)")
        print(f"   阶段: {profile.account_age.value}")
        print(f"   配置: {'✅ 完整' if profile.is_fully_configured else '⚠️ 不完整'}")
        print(f"   IP一致性: {'✅ 一致' if profile.ip_consistent else '❌ 不一致'}")
        print(f"   每日限额:")
        print(f"      • 加群: {profile.config.max_groups_per_day}个")
        print(f"      • 发消息: {profile.config.max_messages_per_hour}条/小时, {profile.config.max_messages_per_day}条/天")
        print(f"      • 陌生人消息: {profile.config.max_stranger_messages_per_day}条/天")
        print(f"      • 好友请求: {profile.config.max_friend_requests_per_day}个/天")
        
        # 测试各种操作限制
        operations = [
            ("join_group", "加群"),
            ("send_message", "发消息"),
            ("friend_request", "好友请求"),
        ]
        
        print(f"   操作检查:")
        for op_code, op_name in operations:
            allowed, reason = warming_manager.check_and_enforce_limits(
                account_id=account_id,
                operation=op_code,
                is_stranger=(op_code == "send_message"),
            )
            status = "✅ 允许" if allowed else f" 禁止"
            print(f"      • {op_name}: {status}")
    
    print("\n✅ 养号策略演示完成\n")


def demo_workflow():
    """演示: 完整工作流程"""
    print("=" * 70)
    print("🎯 演示3: 完整OSINT工作流程")
    print("=" * 70)
    
    workflow_steps = [
        ("1", "操作员创建任务", "选择平台(Telegram) + 类别(freelancer) + 关键词"),
        ("2", "系统选择健康账号", "检查养号状态和IP一致性"),
        ("3", "搜索相关群组", "检查每日加群限额"),
        ("4", "加入群组", "记录操作,更新计数器,随机延迟30-120秒"),
        ("5", "获取群成员", "选择目标用户"),
        ("6", "发起对话", "发送算术题验证(如: 23 + 45 = ?)"),
        ("7", "用户通过验证", "开始拟人化对话"),
        ("8", "AI生成回复", "DeepSeek-V3生成,带打字延迟"),
        ("9", "提取情报", "实体提取→分类标注→可信度评分→去重存储"),
        ("10", "优雅退出", "标记对话完成,清理资源"),
    ]
    
    print("\n📋 工作流程步骤:")
    for step_num, title, desc in workflow_steps:
        print(f"   {step_num}. {title}")
        print(f"      {desc}")
    
    print("\n 安全防护措施:")
    protections = [
        "✓ 算术题验证过滤机器人(~60%过滤率)",
        "✓ 养号策略防止封号(存活率~85%)",
        "✓ 速率限制避免Flood Wait",
        "✓ 行为模拟降低检测风险(打字延迟/阅读延迟)",
        "✓ IP一致性追踪(90天内同一地区)",
        "✓ 一键拉黑功能(快速屏蔽高风险用户)",
        "✓ 媒体组批量发送(提升效率~5倍)",
    ]
    for protection in protections:
        print(f"   {protection}")
    
    print("\n📈 预期效果:")
    metrics = [
        ("账号月存活率", "~85%", "vs 未养号30-40%"),
        ("机器人过滤率", "~60%", "节省LLM调用成本"),
        ("每日产能(单账号)", "3-5条情报", "Telegram平台"),
        ("媒体组发送效率", "~5倍提升", "批量vs逐条"),
    ]
    for metric, value, note in metrics:
        print(f"   • {metric}: {value} ({note})")
    
    print("\n✅ 工作流程演示完成\n")


def main():
    """运行所有演示"""
    print("\n" + "=" * 70)
    print("🚀 Telegram OSINT 系统 - 本地功能演示")
    print("=" * 70 + "\n")
    
    try:
        demo_verification()
        demo_warming_strategy()
        demo_workflow()
        
        print("=" * 70)
        print("🎉 所有演示完成!")
        print("=" * 70)
        
        print("\n📁 Session文件状态:")
        import os
        session_dir = Path(__file__).parent / "sessions"
        if session_dir.exists():
            sessions = list(session_dir.glob("*.session"))
            print(f"   ✅ 找到 {len(sessions)} 个session文件:")
            for s in sessions:
                size_kb = s.stat().st_size / 1024
                print(f"      • {s.name} ({size_kb:.1f} KB)")
        else:
            print(f"   ⚠️ sessions目录不存在")
        
        print("\n 下一步操作:")
        print("   1. 安装依赖:")
        print("      cd backend && python3 -m venv venv && source venv/bin/activate")
        print("      pip install -e '.[dev]'")
        print()
        print("   2. 启动后端服务:")
        print("      uvicorn app.main:app --reload --host 0.0.0.0 --port 8000")
        print()
        print("   3. 启动Celery Worker:")
        print("      celery -A app.workers.tasks worker --loglevel=info")
        print()
        print("   4. 启动前端(新终端):")
        print("      cd frontend && npm run dev")
        print()
        print("   5. 访问系统:")
        print("      • 前端界面: http://localhost:3000")
        print("      • API文档: http://localhost:8000/docs")
        print()
        
    except KeyboardInterrupt:
        print("\n\n⚠️ 演示被用户中断")
    except Exception as e:
        print(f"\n 演示出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
