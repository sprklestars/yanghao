"""
用户拉黑列表管理

功能:
- 添加/移除拉黑用户
- 检查用户是否被拉黑
- 持久化到Redis或内存
"""

import logging
from typing import Set

logger = logging.getLogger(__name__)


class BlockListManager:
    """拉黑列表管理器"""

    def __init__(self):
        # 使用内存存储(生产环境应使用Redis)
        self.blocked_users: Set[str] = set()

    def block_user(self, user_id: str) -> bool:
        """拉黑用户"""
        if user_id in self.blocked_users:
            logger.warning(f"用户 {user_id} 已在拉黑列表中")
            return False

        self.blocked_users.add(user_id)
        logger.info(f"✅ 已拉黑用户: {user_id}")
        return True

    def unblock_user(self, user_id: str) -> bool:
        """取消拉黑用户"""
        if user_id not in self.blocked_users:
            logger.warning(f"用户 {user_id} 不在拉黑列表中")
            return False

        self.blocked_users.discard(user_id)
        logger.info(f"✅ 已取消拉黑用户: {user_id}")
        return True

    def is_blocked(self, user_id: str) -> bool:
        """检查用户是否被拉黑"""
        return user_id in self.blocked_users

    def get_all_blocked(self) -> Set[str]:
        """获取所有拉黑用户"""
        return self.blocked_users.copy()

    def clear(self):
        """清空拉黑列表"""
        self.blocked_users.clear()
        logger.info("🗑️  已清空拉黑列表")


# 全局单例
blocklist_manager = BlockListManager()


def block_user(user_id: str) -> bool:
    """便捷函数: 拉黑用户"""
    return blocklist_manager.block_user(user_id)


def unblock_user(user_id: str) -> bool:
    """便捷函数: 取消拉黑"""
    return blocklist_manager.unblock_user(user_id)


def is_blocked(user_id: str) -> bool:
    """便捷函数: 检查是否拉黑"""
    return blocklist_manager.is_blocked(user_id)
